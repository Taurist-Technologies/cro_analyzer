"""
PDP analysis orchestrator: capture -> validate PDP -> Claude -> result.

One Claude call per analysis, with:
- prompt-cached static system rubric (cache_control on the system block)
- schema-enforced JSON via output_config.format (no repair layer needed)
- exactly-5 quick wins enforced again in code
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import anthropic
from playwright.async_api import Browser
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings
from analyzer.pdp.capture import capture_pdp
from analyzer.pdp.extractor import detect_pdp
from analyzer.pdp.prompts import PDP_SYSTEM_PROMPT, build_user_content
from analyzer.pdp.schema import PDP_ANALYSIS_SCHEMA

logger = logging.getLogger(__name__)

_async_client: Optional[anthropic.AsyncAnthropic] = None


def get_async_anthropic() -> anthropic.AsyncAnthropic:
    global _async_client
    if _async_client is None:
        _async_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _async_client


async def run_pdp_analysis(
    browser: Browser,
    url: str,
    include_screenshots: bool = False,
    progress: Optional[Callable[[int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Full analysis of one product page URL.

    Returns a result dict with status "success" or "not_product_page".
    Screenshots are included under "screenshots" only when
    include_screenshots is True; callers that need them for later retrieval
    should read the "_screenshots" key before stripping it.
    """
    started = time.time()

    capture = await capture_pdp(browser, url, progress=progress)

    desktop_facts = capture["desktop"].get("facts", {}) or {}
    jsonld = capture["desktop"].get("jsonld_products", [])
    is_pdp, signals = detect_pdp(desktop_facts, jsonld)

    # Distinguish "genuinely not a PDP" from "we failed to read the page".
    # If DOM extraction errored, don't confidently tell the user it's not a
    # product page — proceed if any independent signal (JSON-LD) says PDP.
    extraction_failed = "error" in desktop_facts
    if extraction_failed and jsonld:
        is_pdp, signals = True, signals + ["JSON-LD product (DOM extraction degraded)"]

    if not is_pdp and not extraction_failed:
        return {
            "status": "not_product_page",
            "url": url,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "message": (
                "This URL doesn't look like a product detail page — no product "
                "schema, add-to-cart form, or price was found. Please share a "
                "direct link to one of your product pages."
            ),
            "page_title": capture.get("page_title", ""),
        }

    if progress:
        progress(60, "Our PDP specialist model is reviewing your buy box, social proof, and mobile experience...")

    content = build_user_content(url, capture.get("page_title", ""), capture)
    analysis = await _call_claude(content)

    if progress:
        progress(90, "Scoring findings by impact, confidence, and effort...")

    quick_wins = sorted(
        analysis.get("quick_wins", []),
        key=lambda w: w.get("priority_score", 0),
        reverse=True,
    )[:5]

    screenshots = {
        "desktop_above_fold": capture["desktop"]["screenshots"].get("above_fold"),
        "desktop_full_page": capture["desktop"]["screenshots"].get("full_page"),
        "mobile_above_fold": capture["mobile"]["screenshots"].get("above_fold"),
        "mobile_full_page": capture["mobile"]["screenshots"].get("full_page"),
        "buy_box": capture["desktop"]["screenshots"].get("buy_box"),
    }

    result: Dict[str, Any] = {
        "status": "success",
        "url": url,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "page_title": capture.get("page_title", ""),
        "page_type_signals": signals,
        "total_issues_identified": analysis.get("total_issues_identified", len(quick_wins)),
        "issues": quick_wins,
        "scorecards": analysis.get("scorecards", {}),
        "executive_summary": analysis.get("executive_summary", {}),
        "conversion_rate_increase_potential": analysis.get("conversion_rate_increase_potential", {}),
        "product": (capture["desktop"].get("jsonld_products") or [{}])[0],
        "performance": {
            "desktop": capture["desktop"].get("metrics", {}),
            "mobile": capture["mobile"].get("metrics", {}),
        },
        "add_to_cart_test": capture["desktop"].get("atc_test", {}),
        "analysis_duration_seconds": round(time.time() - started, 2),
        "_screenshots": screenshots,
    }

    if include_screenshots:
        result["screenshots"] = screenshots

    return result


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(
        (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError)
    ),
    reraise=True,
)
async def _call_claude(content) -> Dict[str, Any]:
    """Single structured-output call. The API validates against the schema,
    so json.loads on the text block cannot fail on well-formed responses."""
    client = get_async_anthropic()

    response = await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=settings.MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": PDP_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": content}],
        output_config={
            "format": {"type": "json_schema", "schema": PDP_ANALYSIS_SCHEMA}
        },
    )

    usage = response.usage
    logger.info(
        "Claude call complete: in=%s cached=%s out=%s",
        usage.input_tokens,
        getattr(usage, "cache_read_input_tokens", 0),
        usage.output_tokens,
    )

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "Claude response was truncated at max_tokens; raise MAX_TOKENS. "
            "The structured JSON is incomplete and cannot be parsed."
        )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise RuntimeError(f"No text block in Claude response (stop_reason={response.stop_reason})")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Structured output was not valid JSON (stop_reason={response.stop_reason}): {e}")


async def analyze_url_standalone(url: str, include_screenshots: bool = False) -> Dict[str, Any]:
    """Sync-endpoint path: launch a throwaway browser for one analysis."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
            ],
        )
        try:
            return await asyncio.wait_for(
                run_pdp_analysis(browser, url, include_screenshots),
                timeout=settings.ANALYSIS_TIMEOUT,
            )
        finally:
            await browser.close()
