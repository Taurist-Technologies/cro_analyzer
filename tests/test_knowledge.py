"""Tests for the 3-tier knowledge grounding chain (Qdrant mocked)."""

import asyncio

import pytest

import analyzer.pdp.knowledge as knowledge
from analyzer.pdp.knowledge import (
    assemble_grounding,
    build_queries,
    format_grounding_block,
    retrieve_grounding,
)
from config import settings

DESKTOP_FACTS = {
    "atc": {"found": True, "above_fold": True, "text": "Add to Cart", "sticky": False},
    "price": {"found": True, "near_atc": False, "has_compare_at_price": False, "installment_options": []},
    "gallery": {"image_count": 2, "has_video": False},
    "reviews": {"widget_found": False, "star_rating_visible": False},
    "shipping": {"shipping_mention_near_buybox": False, "returns_mention_near_buybox": False,
                 "guarantee_mention": False, "stock_urgency_mention": False},
    "variants": {"uses_dropdowns": True, "has_size_guide": False},
}
MOBILE_FACTS = {"atc": {"found": True, "above_fold": False, "sticky": False}}
JSONLD = [{"name": "Foldable Booster Seat", "brand": "Acme", "review_count": "312"}]


def _hit(pid, score, client=None, title="t", issue="i", recs=None, source=None):
    payload = {"title": title, "issue": issue, "recommendations": recs or ["r1"]}
    if client:
        payload["client"] = client
    if source:
        payload["source"] = source
    return {"id": pid, "score": score, "payload": payload}


class TestBuildQueries:
    def test_queries_reflect_observed_facts(self):
        queries = dict(build_queries(DESKTOP_FACTS, MOBILE_FACTS, JSONLD))
        assert "below the fold on mobile" in queries["mobile"]
        assert "no sticky add to cart bar" in queries["mobile"]
        assert "no visible reviews" in queries["social_proof"]
        assert "no shipping info near CTA" in queries["shipping_returns"]
        assert "far from the CTA" in queries["buy_box"]
        assert "Foldable Booster Seat" in queries["buy_box"]

    def test_handles_empty_facts(self):
        queries = build_queries({}, {}, [])
        assert len(queries) == 6  # all categories still queried


class TestAssembleGrounding:
    def test_audit_patterns_take_precedence(self):
        cats = ["buy_box", "mobile"]
        audit = [[_hit("a1", 0.8, client="Mifold")], []]
        knowledge_hits = [[_hit("k1", 0.9, source="Sticky CTA study")], [_hit("k2", 0.7, source="Mobile study")]]
        g = assemble_grounding(cats, audit, knowledge_hits)
        by_cat = {p["category"]: p for p in g["patterns"]}
        # buy_box had an audit hit -> knowledge NOT consulted for that category
        assert by_cat["buy_box"]["tier"] == "proprietary_audit"
        assert by_cat["buy_box"]["source"] == "Mifold"
        # mobile had no audit hit -> knowledge fills the gap
        assert by_cat["mobile"]["tier"] == "knowledge_base"
        assert g["tier"] == "mixed"

    def test_pure_audit_tier(self):
        g = assemble_grounding(["buy_box"], [[_hit("a1", 0.8, client="Retrospec")]], [[]])
        assert g["tier"] == "proprietary_audit"
        assert g["sources"] == ["Retrospec"]

    def test_pure_knowledge_tier(self):
        g = assemble_grounding(["buy_box"], [[]], [[_hit("k1", 0.7, source="doc")]])
        assert g["tier"] == "knowledge_base"

    def test_nothing_found_returns_none(self):
        assert assemble_grounding(["buy_box"], [[]], [[]]) is None

    def test_dedupes_across_categories(self):
        same = _hit("dup", 0.8, client="Mifold")
        g = assemble_grounding(["buy_box", "mobile"], [[same], [same]], [[], []])
        assert len(g["patterns"]) == 1

    def test_global_cap(self, monkeypatch):
        monkeypatch.setattr(settings, "GROUNDING_MAX_SNIPPETS", 3)
        cats = ["c1", "c2", "c3"]
        audit = [[_hit(f"a{i}", 0.8, client="X"), _hit(f"b{i}", 0.7, client="Y")] for i in range(3)]
        g = assemble_grounding(cats, audit, [[], [], []])
        assert len(g["patterns"]) == 3


class TestRetrieveGrounding:
    def test_disabled_without_config_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "QDRANT_URL", "")
        result = asyncio.run(retrieve_grounding(DESKTOP_FACTS, MOBILE_FACTS, JSONLD))
        assert result is None

    def test_any_failure_degrades_to_none(self, monkeypatch):
        monkeypatch.setattr(settings, "QDRANT_URL", "https://qdrant.example")
        monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "k")

        async def boom(*a, **kw):
            raise RuntimeError("embedding API down")

        monkeypatch.setattr(knowledge, "_retrieve", boom)
        result = asyncio.run(retrieve_grounding(DESKTOP_FACTS, MOBILE_FACTS, JSONLD))
        assert result is None

    def test_full_flow_with_mocked_backends(self, monkeypatch):
        monkeypatch.setattr(settings, "QDRANT_URL", "https://qdrant.example")
        monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "k")

        async def fake_embed(client, texts, provider, model, api_key, input_type="query"):
            return [[0.1, 0.2] for _ in texts]

        async def fake_search(client, collection, vectors, limit, score_threshold):
            if collection == settings.QDRANT_AUDIT_COLLECTION:
                # audit hit only for the first category
                return [[_hit("a1", 0.9, client="Tommy Docks")]] + [[] for _ in vectors[1:]]
            return [[_hit(f"k{i}", 0.6, source="brain")] for i in range(len(vectors))]

        monkeypatch.setattr(knowledge, "embed_texts", fake_embed)
        monkeypatch.setattr(knowledge, "qdrant_batch_search", fake_search)

        g = asyncio.run(retrieve_grounding(DESKTOP_FACTS, MOBILE_FACTS, JSONLD))
        assert g["tier"] == "mixed"
        assert "Tommy Docks" in g["sources"]
        tiers = {p["tier"] for p in g["patterns"]}
        assert tiers == {"proprietary_audit", "knowledge_base"}


class TestFormatBlock:
    def test_empty_grounding_renders_nothing(self):
        assert format_grounding_block(None) == ""

    def test_provenance_labels(self):
        g = assemble_grounding(
            ["buy_box", "mobile"],
            [[_hit("a1", 0.8, client="Annabella", title="Sticky ATC missing")], []],
            [[], [_hit("k1", 0.6, source="thumb-zone research")]],
        )
        block = format_grounding_block(g)
        assert "[AUDIT — Annabella]" in block
        assert "[KNOWLEDGE BASE]" in block
        assert "chain of command" in block
