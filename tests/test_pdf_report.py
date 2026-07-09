"""PDF report generation against the new PDP result shape."""

from utils.reporting.pdf import generate_pdf, register_fonts


def _sample_result():
    quick_win = {
        "title": "ATC button below the fold on mobile",
        "element": "Add-to-cart button",
        "viewport": "mobile",
        "whats_wrong": "The add-to-cart button sits 1200px down the mobile page.",
        "why_it_matters": "Mobile users must scroll before they can buy.",
        "recommendations": [
            "Add a sticky add-to-cart bar on mobile",
            "Move variant pickers above the CTA",
        ],
        "suggested_copy": "Add to Cart — Free Shipping Over $50",
        "impact": "high",
        "effort": "low",
        "priority_score": 92,
        "priority_rationale": "(9x9)/1",
    }
    return {
        "status": "success",
        "url": "https://shop.test/products/widget",
        "analyzed_at": "2026-07-09T12:00:00+00:00",
        "total_issues_identified": 11,
        "issues": [dict(quick_win) for _ in range(5)],
        "scorecards": {
            "buy_box": {"score": 55, "color": "yellow", "rationale": "r"},
            "product_content": {"score": 70, "color": "yellow", "rationale": "r"},
            "social_proof": {"score": 40, "color": "red", "rationale": "r"},
            "mobile_experience": {"score": 60, "color": "yellow", "rationale": "r"},
            "page_speed": {"score": 80, "color": "green", "rationale": "r"},
        },
        "executive_summary": {"overview": "Overview text.", "how_to_act": "Act now."},
        "conversion_rate_increase_potential": {
            "percentage": "8-15%",
            "confidence": "Medium",
            "rationale": "r",
        },
    }


def test_pdf_generates_in_memory_from_new_result_shape():
    register_fonts()
    buf = generate_pdf(_sample_result(), output_path=None)
    data = buf.read()
    assert data[:4] == b"%PDF"
    assert len(data) > 5000


def test_pdf_tolerates_old_cached_shape():
    # Cached pre-rebuild results may still be fetched for PDF generation
    old = _sample_result()
    for issue in old["issues"]:
        issue.pop("whats_wrong")
        issue["description"] = "Old-format description"
        issue.pop("recommendations")
        issue["recommendation"] = "line one\nline two"
    old["scorecards"] = {
        "site_performance": {"score": 50, "color": "yellow", "rationale": "r"},
        "conversion_potential": {"score": 50, "color": "yellow", "rationale": "r"},
        "mobile_experience": {"score": 50, "color": "yellow", "rationale": "r"},
    }
    register_fonts()
    buf = generate_pdf(old, output_path=None)
    assert buf.read()[:4] == b"%PDF"
