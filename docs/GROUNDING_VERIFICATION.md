# Knowledge Grounding — Live Verification

**Status: VERIFIED (2026-07-10)** — previous BLOCKED status resolved after the
environment network policy was updated to allow the Qdrant cluster and
api.openai.com.

## Cluster inventory

| Collection | Points | Vectors | Role |
|---|---|---|---|
| `taurist_audit_patterns` | 983 | 1536-dim, Cosine (unnamed) | Tier 1 — proprietary e-comm audit patterns (16 clients) |
| `slash_cro_knowledge` | 2,184 | 1536-dim, Cosine (unnamed) | Tier 2 — CRO knowledge brain |

`slash_cro_knowledge` uses an unnamed default vector at 1536 dims — consistent
with `text-embedding-3-small` and with the search request shape in
`analyzer/pdp/knowledge.py`. No code changes were required.

## Corpus sync

`python3 scripts/sync_audit_library.py` embedded and upserted **983 patterns
across 16 clients** (Annabella, Drunken Cookies, Her Fantasy Box, Hibernate,
Joseph Nguyen, Juvenon, Lawn Chair USA, Liry's Jewelry, Majestic Fountains,
Mifold, New Wire Marine, Retrospec, Salty Captain, Tommy Docks, Tools for
Wellness, X Audit). Point count confirmed post-sync. IDs are deterministic —
re-running the script after corpus updates modifies points in place.

## Live retrieval test

Input: simulated PDP facts (ATC below fold, no sticky CTA, price far from CTA,
2 images, no video, no reviews, no shipping/returns near buy box, dropdown
variants) for a fictional "Insulated Fishing Cooler".

Result: **1.76s end-to-end**, tier = `proprietary_audit`, 10 patterns across
5 categories, 8 distinct client sources. Sample matches (score → source):

- buy_box 0.696 → Tools for Wellness: "Add to Cart area is not visually dominant and has competing friction"
- buy_box 0.684 → Her Fantasy Box: "No sticky Add To Cart / Buy Now button"
- mobile 0.595 → Salty Captain: "No sticky Add-to-Cart button on product pages"
- shipping_returns 0.550 → Tools for Wellness: "No policy-accurate trust row under the product page CTA"
- social_proof 0.532 → Tommy Docks: "Products have no or very few reviews and review stars"
- product_content 0.486 → Retrospec: "Too few product images and no lifestyle imagery in the gallery"

Raw (unthresholded) score distributions: relevant audit hits 0.47–0.70;
knowledge-brain hits 0.52–0.55. The default thresholds
(`AUDIT_SCORE_THRESHOLD=0.40`, `KNOWLEDGE_SCORE_THRESHOLD=0.40`) sit below the
relevant band and were left unchanged.

## Production checklist

- [x] `taurist_audit_patterns` populated (983 points)
- [x] Live retrieval verified against both collections
- [ ] Set `QDRANT_URL`, `QDRANT_API_KEY`, `EMBEDDING_API_KEY` on the Render
      web + worker services (feature stays off / tier-3 without them)
- [ ] Fix the "Drunken Cookies" Notion page (it largely contains Mifold
      content — an import anomaly), re-extract that file, re-run the sync
- [ ] Rotate the Qdrant + OpenAI keys shared in chat once things are stable
