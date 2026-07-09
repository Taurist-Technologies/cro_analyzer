"""
3-tier knowledge grounding for PDP analysis.

Chain of command for recommendations:
  Tier 1 — proprietary audit patterns (Notion e-comm audit library, indexed
           into the Qdrant collection QDRANT_AUDIT_COLLECTION)
  Tier 2 — the general CRO knowledge brain (QDRANT_KNOWLEDGE_COLLECTION)
  Tier 3 — the model's built-in expert rubric (always present)

The precedence is applied per element category rather than as a global
sequential fallback: we query both collections in parallel (fast), then for
each category prefer audit hits above AUDIT_SCORE_THRESHOLD and only fill
gaps from the knowledge brain. Every snippet keeps its provenance so Claude
can cite "our audit of <client>".

Design constraints:
- Retrieval must NEVER fail or delay an analysis: everything is wrapped,
  time-boxed by GROUNDING_TIMEOUT_SECONDS, and returns None on any problem
  (which simply means tier 3 — the pre-grounding behavior).
- Queries are built from OBSERVED page facts, not generic strings, so
  retrieval is specific to what's actually wrong with this page.
- No qdrant-client / sentence-transformers deps: plain httpx against the
  Qdrant REST API and a hosted embedding API (Voyage or OpenAI).
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from config import settings

logger = logging.getLogger(__name__)

EMBEDDING_ENDPOINTS = {
    "voyage": "https://api.voyageai.com/v1/embeddings",
    "openai": "https://api.openai.com/v1/embeddings",
}


def grounding_enabled() -> bool:
    return bool(settings.QDRANT_URL and settings.EMBEDDING_API_KEY)


# ---------------------------------------------------------------------------
# Query construction — observed facts become retrieval queries
# ---------------------------------------------------------------------------

def build_queries(
    desktop_facts: Dict[str, Any],
    mobile_facts: Dict[str, Any],
    jsonld_products: List[Dict[str, Any]],
) -> List[Tuple[str, str]]:
    """Return (category, query_text) pairs describing this page's state."""
    product = (jsonld_products or [{}])[0] or {}
    context = " ".join(
        str(x) for x in (product.get("name"), product.get("brand")) if x
    )

    atc = desktop_facts.get("atc", {}) or {}
    price = desktop_facts.get("price", {}) or {}
    gallery = desktop_facts.get("gallery", {}) or {}
    reviews = desktop_facts.get("reviews", {}) or {}
    shipping = desktop_facts.get("shipping", {}) or {}
    variants = desktop_facts.get("variants", {}) or {}
    m_atc = (mobile_facts or {}).get("atc", {}) or {}

    def yn(flag, yes, no):
        return yes if flag else no

    queries = [
        (
            "buy_box",
            f"ecommerce product page add to cart buy box: CTA {yn(atc.get('found'), 'present', 'missing')}, "
            f"{yn(atc.get('above_fold'), 'above the fold', 'below the fold')}, "
            f"button text '{atc.get('text') or 'unknown'}', "
            f"price {yn(price.get('near_atc'), 'near the CTA', 'far from the CTA')}, "
            f"{yn(price.get('has_compare_at_price'), 'compare-at price anchoring shown', 'no price anchoring')}, "
            f"{yn(variants.get('uses_dropdowns'), 'variant dropdowns instead of swatches', 'variant swatches')} "
            f"{context}",
        ),
        (
            "shipping_returns",
            f"product page shipping returns risk reversal near buy box: "
            f"{yn(shipping.get('shipping_mention_near_buybox'), 'shipping info shown', 'no shipping info near CTA')}, "
            f"{yn(shipping.get('returns_mention_near_buybox'), 'returns policy shown', 'no returns policy near CTA')}, "
            f"{yn(shipping.get('guarantee_mention'), 'guarantee mentioned', 'no guarantee')} {context}",
        ),
        (
            "social_proof",
            f"product page reviews ratings social proof: "
            f"{yn(reviews.get('widget_found'), 'review widget present', 'no visible reviews')}, "
            f"{yn(reviews.get('star_rating_visible'), 'star rating visible', 'no star rating near title')}, "
            f"schema review count {product.get('review_count') or 'none'} {context}",
        ),
        (
            "product_content",
            f"product page images gallery content quality: {gallery.get('image_count', 0)} images, "
            f"{yn(gallery.get('has_video'), 'video present', 'no product video')}, "
            f"{yn(variants.get('has_size_guide'), 'size guide present', 'no size guide')} {context}",
        ),
        (
            "mobile",
            f"mobile product page experience: add to cart "
            f"{yn(m_atc.get('above_fold'), 'above the fold on mobile', 'below the fold on mobile')}, "
            f"{yn(m_atc.get('sticky'), 'sticky CTA present', 'no sticky add to cart bar')} {context}",
        ),
        (
            "urgency",
            f"product page urgency scarcity payment options: "
            f"{yn(price.get('installment_options'), 'installments offered', 'no installment options')}, "
            f"{yn(shipping.get('stock_urgency_mention'), 'stock urgency shown', 'no stock or urgency signals')} {context}",
        ),
    ]
    return queries


# ---------------------------------------------------------------------------
# Embeddings + Qdrant REST
# ---------------------------------------------------------------------------

async def embed_texts(
    client: httpx.AsyncClient,
    texts: List[str],
    provider: str,
    model: str,
    api_key: str,
    input_type: str = "query",
) -> List[List[float]]:
    """Batch-embed via a hosted API. input_type only applies to Voyage."""
    if provider not in EMBEDDING_ENDPOINTS:
        raise ValueError(f"Unknown embedding provider: {provider!r}")

    payload: Dict[str, Any] = {"model": model, "input": texts}
    if provider == "voyage":
        payload["input_type"] = input_type

    resp = await client.post(
        EMBEDDING_ENDPOINTS[provider],
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return [row["embedding"] for row in sorted(data, key=lambda r: r.get("index", 0))]


async def qdrant_batch_search(
    client: httpx.AsyncClient,
    collection: str,
    vectors: List[List[float]],
    limit: int,
    score_threshold: float,
) -> List[List[Dict[str, Any]]]:
    """One HTTP round trip for all category queries against a collection."""
    resp = await client.post(
        f"{settings.QDRANT_URL.rstrip('/')}/collections/{collection}/points/search/batch",
        json={
            "searches": [
                {
                    "vector": v,
                    "limit": limit,
                    "score_threshold": score_threshold,
                    "with_payload": True,
                }
                for v in vectors
            ]
        },
        headers={"api-key": settings.QDRANT_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["result"]


# ---------------------------------------------------------------------------
# Precedence assembly
# ---------------------------------------------------------------------------

def assemble_grounding(
    categories: List[str],
    audit_results: List[List[Dict[str, Any]]],
    knowledge_results: List[List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """
    Apply the chain of command per category: audit patterns first, knowledge
    brain fills categories with no audit match. Dedupes by point id and caps
    the total to keep prompt tokens bounded.
    """
    patterns: List[Dict[str, Any]] = []
    seen_ids = set()
    used_audit = used_knowledge = False

    for i, category in enumerate(categories):
        audit_hits = (audit_results[i] if i < len(audit_results) else [])[:2]
        fresh_audit = [h for h in audit_hits if h.get("id") not in seen_ids]

        if fresh_audit:
            used_audit = True
            for hit in fresh_audit:
                seen_ids.add(hit.get("id"))
                patterns.append(_pattern_from_hit(hit, category, tier="proprietary_audit"))
            continue  # audit patterns found — knowledge brain not consulted for this category

        knowledge_hits = (knowledge_results[i] if i < len(knowledge_results) else [])[:2]
        for hit in knowledge_hits:
            if hit.get("id") in seen_ids:
                continue
            seen_ids.add(hit.get("id"))
            used_knowledge = True
            patterns.append(_pattern_from_hit(hit, category, tier="knowledge_base"))

    if not patterns:
        return None

    patterns = patterns[: settings.GROUNDING_MAX_SNIPPETS]
    tier = (
        "mixed" if (used_audit and used_knowledge)
        else "proprietary_audit" if used_audit
        else "knowledge_base"
    )
    return {
        "tier": tier,
        "patterns": patterns,
        "sources": sorted({p["source"] for p in patterns if p.get("source")}),
    }


def _pattern_from_hit(hit: Dict[str, Any], category: str, tier: str) -> Dict[str, Any]:
    payload = hit.get("payload") or {}
    recommendations = payload.get("recommendations") or []
    if isinstance(recommendations, str):
        recommendations = [recommendations]
    return {
        "tier": tier,
        "category": category,
        "score": round(float(hit.get("score", 0.0)), 3),
        "source": payload.get("client") or payload.get("source") or payload.get("title") or "",
        "title": payload.get("title", ""),
        "issue": payload.get("issue") or payload.get("text") or payload.get("content") or "",
        "why_it_matters": payload.get("why_it_matters", ""),
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def retrieve_grounding(
    desktop_facts: Dict[str, Any],
    mobile_facts: Dict[str, Any],
    jsonld_products: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Fetch grounding snippets for this page. Returns None whenever the feature
    is disabled or anything goes wrong — the analysis then simply runs on the
    built-in expert rubric (tier 3), exactly as before this feature existed.
    """
    if not grounding_enabled():
        return None
    try:
        return await asyncio.wait_for(
            _retrieve(desktop_facts, mobile_facts, jsonld_products),
            timeout=settings.GROUNDING_TIMEOUT_SECONDS,
        )
    except Exception as e:
        logger.warning(f"Knowledge grounding unavailable, falling back to expert tier: {e}")
        return None


async def _retrieve(desktop_facts, mobile_facts, jsonld_products) -> Optional[Dict[str, Any]]:
    queries = build_queries(desktop_facts, mobile_facts, jsonld_products)
    categories = [c for c, _ in queries]
    texts = [t for _, t in queries]

    k_provider = settings.KNOWLEDGE_EMBEDDING_PROVIDER or settings.EMBEDDING_PROVIDER
    k_model = settings.KNOWLEDGE_EMBEDDING_MODEL or settings.EMBEDDING_MODEL
    k_key = settings.KNOWLEDGE_EMBEDDING_API_KEY or settings.EMBEDDING_API_KEY
    same_embedding = (k_provider, k_model) == (settings.EMBEDDING_PROVIDER, settings.EMBEDDING_MODEL)

    async with httpx.AsyncClient() as client:
        embed_jobs = [
            embed_texts(
                client, texts,
                settings.EMBEDDING_PROVIDER, settings.EMBEDDING_MODEL,
                settings.EMBEDDING_API_KEY,
            )
        ]
        if not same_embedding:
            embed_jobs.append(embed_texts(client, texts, k_provider, k_model, k_key))
        embeddings = await asyncio.gather(*embed_jobs)
        audit_vectors = embeddings[0]
        knowledge_vectors = embeddings[0] if same_embedding else embeddings[1]

        audit_results, knowledge_results = await asyncio.gather(
            qdrant_batch_search(
                client, settings.QDRANT_AUDIT_COLLECTION, audit_vectors,
                limit=3, score_threshold=settings.AUDIT_SCORE_THRESHOLD,
            ),
            qdrant_batch_search(
                client, settings.QDRANT_KNOWLEDGE_COLLECTION, knowledge_vectors,
                limit=3, score_threshold=settings.KNOWLEDGE_SCORE_THRESHOLD,
            ),
            return_exceptions=True,
        )

    # A missing/unreachable collection degrades that tier, not the analysis
    if isinstance(audit_results, BaseException):
        logger.warning(f"Audit collection search failed: {audit_results}")
        audit_results = [[] for _ in categories]
    if isinstance(knowledge_results, BaseException):
        logger.warning(f"Knowledge collection search failed: {knowledge_results}")
        knowledge_results = [[] for _ in categories]

    return assemble_grounding(categories, audit_results, knowledge_results)


def format_grounding_block(grounding: Optional[Dict[str, Any]]) -> str:
    """Render retrieved patterns for the user message (after the cached prefix)."""
    if not grounding or not grounding.get("patterns"):
        return ""
    lines = [
        "## Proprietary knowledge grounding",
        "",
        "The following patterns were retrieved for THIS page's observed state. "
        "Apply the chain of command: patterns labeled [AUDIT — <client>] come from "
        "our own past e-commerce audits and take precedence — ground matching "
        "recommendations in them and cite the client. Patterns labeled [KNOWLEDGE "
        "BASE] are our curated CRO research — use them where no audit pattern "
        "applies. Where neither covers a finding, rely on expert CRO practice. "
        "Never force an irrelevant pattern onto this page.",
        "",
    ]
    for p in grounding["patterns"]:
        label = f"[AUDIT — {p['source']}]" if p["tier"] == "proprietary_audit" else "[KNOWLEDGE BASE]"
        lines.append(f"### {label} ({p['category']}, relevance {p['score']})")
        if p.get("title"):
            lines.append(f"**{p['title']}**")
        if p.get("issue"):
            lines.append(f"Issue: {p['issue']}")
        if p.get("why_it_matters"):
            lines.append(f"Why it matters: {p['why_it_matters']}")
        if p.get("recommendations"):
            lines.append("Recommendations: " + " | ".join(p["recommendations"][:4]))
        lines.append("")
    return "\n".join(lines)
