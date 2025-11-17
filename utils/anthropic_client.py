"""
Anthropic API client utilities for CRO Analyzer.

This module contains functions for interacting with the Anthropic Claude API
with automatic retry logic for transient failures.
"""

import anthropic
import os
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# Lazy initialization of Anthropic client
_anthropic_client = None


def get_anthropic_client():
    """Get or create the Anthropic client instance."""
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _anthropic_client


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(
        (anthropic.APIConnectionError, anthropic.RateLimitError)
    ),
    reraise=True,
)
def call_anthropic_api_with_retry(
    cro_prompt: str,
    url: str,
    page_title: str,
    section_screenshots: list,
    mobile_screenshot: str = None,
    interaction_results: dict = None,
):
    """
    Calls Anthropic API with automatic retry logic for transient failures.
    Uses section-based analysis with multiple screenshots per page section.

    Retries up to 3 times for:
    - APIConnectionError (network issues)
    - RateLimitError (rate limit exceeded)

    Does NOT retry for:
    - AuthenticationError (bad API key)
    - InvalidRequestError (malformed request)
    - Other permanent errors

    Args:
        cro_prompt: The CRO analysis prompt with section context
        url: Website URL being analyzed
        page_title: Page title
        section_screenshots: List of base64-encoded section screenshots
        mobile_screenshot: Base64-encoded mobile screenshot (optional)
        interaction_results: Results from InteractionTester (optional)

    Returns:
        Anthropic message response
    """
    client = get_anthropic_client()

    # Build content array with section screenshots
    content = []

    # Add all section screenshots first
    for section_screenshot in section_screenshots:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": section_screenshot,
            },
        })

    # Add mobile screenshot if provided
    if mobile_screenshot:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": mobile_screenshot,
            },
        })

    # Format interaction test results if provided
    interaction_text = ""
    if interaction_results:
        from utils.interaction_tester import InteractionTester
        # Create temporary tester to use formatting method
        temp_tester = type('obj', (object,), {'test_results': interaction_results})()
        interaction_text = f"\n\n{InteractionTester.format_for_claude_prompt(temp_tester)}\n"

    # Add text prompt
    content.append({
        "type": "text",
        "text": f"""{cro_prompt}

Website URL: {url}
Page Title: {page_title}
{interaction_text}
Please analyze these section screenshots and provide your findings in the JSON format specified above.""",
    })

    return client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,  # Always use 4000 for section-based analysis
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
    )
