"""Unit tests for the pure-Python parts of the PDP extractor."""

from analyzer.pdp.extractor import _find_products, _summarize_product, detect_pdp


PRODUCT_NODE = {
    "@type": "Product",
    "name": "Widget",
    "brand": {"@type": "Brand", "name": "Acme"},
    "image": ["/a.jpg", "/b.jpg"],
    "description": "A widget.",
    "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.5", "reviewCount": "88"},
    "offers": [{"@type": "Offer", "price": "19.99", "priceCurrency": "USD", "availability": "https://schema.org/InStock"}],
}


class TestFindProducts:
    def test_finds_top_level_product(self):
        assert len(_find_products(PRODUCT_NODE)) == 1

    def test_finds_product_in_graph(self):
        doc = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage"}, PRODUCT_NODE]}
        assert len(_find_products(doc)) == 1

    def test_finds_product_in_list(self):
        assert len(_find_products([PRODUCT_NODE, {"@type": "BreadcrumbList"}])) == 1

    def test_handles_type_as_list(self):
        node = dict(PRODUCT_NODE, **{"@type": ["Product", "IndividualProduct"]})
        assert len(_find_products(node)) == 1

    def test_ignores_non_products(self):
        assert _find_products({"@type": "Organization"}) == []


class TestSummarizeProduct:
    def test_summarizes_offers_list_and_brand_object(self):
        s = _summarize_product(PRODUCT_NODE)
        assert s["name"] == "Widget"
        assert s["brand"] == "Acme"
        assert s["price"] == "19.99"
        assert s["currency"] == "USD"
        assert s["availability"] == "InStock"
        assert s["rating_value"] == "4.5"
        assert s["review_count"] == "88"
        assert s["image_count"] == 2

    def test_handles_missing_fields(self):
        s = _summarize_product({"@type": "Product"})
        assert s["price"] is None
        assert s["availability"] is None
        assert s["image_count"] == 0


class TestDetectPdp:
    def test_jsonld_alone_qualifies(self):
        is_pdp, signals = detect_pdp({}, [{"name": "Widget"}])
        assert is_pdp and signals

    def test_og_type_product_qualifies(self):
        is_pdp, _ = detect_pdp({"meta": {"og_type": "product"}}, [])
        assert is_pdp

    def test_atc_plus_price_qualifies(self):
        is_pdp, _ = detect_pdp({"atc": {"found": True}, "price": {"found": True}, "meta": {}}, [])
        assert is_pdp

    def test_plain_page_rejected(self):
        is_pdp, signals = detect_pdp(
            {"atc": {"found": False}, "price": {"found": False}, "meta": {"og_type": "website"}}, []
        )
        assert not is_pdp and signals == []
