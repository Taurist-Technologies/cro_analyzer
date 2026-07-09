"""
End-to-end pipeline test against a local PDP fixture with the Claude call
mocked. Exercises: navigation, overlay handling, screenshots, DOM fact
extraction, JSON-LD parsing, PDP detection, ATC interaction test, and
result assembly — everything except the paid API call.

Requires Playwright Chromium. Skipped automatically if it can't launch.
"""

import asyncio
import http.server
import json
import threading
from pathlib import Path

import pytest

import analyzer.pdp.capture as capture_mod
from analyzer.pdp.analysis import run_pdp_analysis

FIXTURES = Path(__file__).parent / "fixtures"

FAKE_ANALYSIS = {
    "executive_summary": {"overview": "Solid PDP with gaps.", "how_to_act": "Fix the top item first."},
    "quick_wins": [
        {
            "title": f"Finding {i}",
            "element": "Add-to-cart button",
            "viewport": "both",
            "whats_wrong": "x",
            "why_it_matters": "y",
            "recommendations": ["do z"],
            "suggested_copy": None,
            "impact": "high",
            "effort": "low",
            "priority_score": 90 - i,
            "priority_rationale": "r",
        }
        for i in range(6)  # deliberately 6 to verify truncation to 5
    ],
    "scorecards": {
        k: {"score": 70, "color": "yellow", "rationale": "r"}
        for k in ("buy_box", "product_content", "social_proof", "mobile_experience", "page_speed")
    },
    "conversion_rate_increase_potential": {"percentage": "8-15%", "confidence": "Medium", "rationale": "r"},
    "total_issues_identified": 11,
}


@pytest.fixture(scope="module")
def fixture_server():
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(FIXTURES), **kw)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture()
def browser_and_loop():
    from playwright.async_api import async_playwright

    loop = asyncio.new_event_loop()

    async def launch():
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        return pw, browser

    try:
        pw, browser = loop.run_until_complete(launch())
    except Exception as e:
        loop.close()
        pytest.skip(f"Chromium unavailable: {e}")

    yield loop, browser

    async def teardown():
        await browser.close()
        await pw.stop()

    loop.run_until_complete(teardown())
    loop.close()


def test_full_pipeline_on_fixture_pdp(fixture_server, browser_and_loop, monkeypatch):
    loop, browser = browser_and_loop

    # The fixture server is loopback; disable the redirect SSRF re-check for the test
    monkeypatch.setattr(capture_mod, "_recheck_final_url", lambda url: None)

    async def fake_call_claude(content):
        # sanity: images + facts text present in the outgoing request
        images = [b for b in content if b.get("type") == "image"]
        texts = [b["text"] for b in content if b.get("type") == "text"]
        assert len(images) >= 4, "expected desktop+mobile above-fold and full-page shots"
        facts_blob = texts[-1]
        assert "schema_org_products" in facts_blob
        assert "Foldable Booster Seat" in facts_blob
        return json.loads(json.dumps(FAKE_ANALYSIS))

    import analyzer.pdp.analysis as analysis_mod
    monkeypatch.setattr(analysis_mod, "_call_claude", fake_call_claude)

    progress_events = []
    result = loop.run_until_complete(
        run_pdp_analysis(
            browser,
            f"{fixture_server}/pdp.html",
            include_screenshots=False,
            progress=lambda p, s: progress_events.append((p, s)),
        )
    )

    assert result["status"] == "success"
    assert len(result["issues"]) == 5, "quick wins must be truncated to exactly 5"
    assert result["issues"][0]["priority_score"] >= result["issues"][-1]["priority_score"]
    assert set(result["scorecards"]) == {"buy_box", "product_content", "social_proof", "mobile_experience", "page_speed"}

    # Deterministic extraction verified end-to-end
    product = result["product"]
    assert product["name"] == "Foldable Booster Seat"
    assert product["review_count"] == "312"
    assert result["page_type_signals"]

    # ATC interaction test clicked the button and saw the cart count change
    assert result["add_to_cart_test"]["attempted"] is True
    assert result["add_to_cart_test"]["cart_responded"] is True

    # Real metrics captured
    assert result["performance"]["desktop"].get("request_count") is not None

    # Screenshots kept out of the payload but available under _screenshots
    assert "screenshots" not in result
    shots = result["_screenshots"]
    assert shots["desktop_above_fold"] and shots["mobile_full_page"]

    assert progress_events, "progress callback should fire"


def test_non_pdp_page_is_rejected_fast(fixture_server, browser_and_loop, monkeypatch):
    loop, browser = browser_and_loop
    monkeypatch.setattr(capture_mod, "_recheck_final_url", lambda url: None)

    # Plain page with no product signals
    (FIXTURES / "not_a_pdp.html").write_text(
        "<html><head><title>About us</title></head><body><h1>Our story</h1><p>Hello.</p></body></html>"
    )

    called = {"claude": False}

    async def fake_call_claude(content):
        called["claude"] = True
        return {}

    import analyzer.pdp.analysis as analysis_mod
    monkeypatch.setattr(analysis_mod, "_call_claude", fake_call_claude)

    result = loop.run_until_complete(
        run_pdp_analysis(browser, f"{fixture_server}/not_a_pdp.html", include_screenshots=False)
    )

    assert result["status"] == "not_product_page"
    assert "product" in result["message"].lower()
    assert called["claude"] is False, "must not spend API tokens on non-PDPs"
