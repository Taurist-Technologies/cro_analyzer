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
    screenshot_base64: str, cro_prompt: str, url: str, page_title: str, deep_info: bool
):
    """
    Calls Anthropic API with automatic retry logic for transient failures.

    Retries up to 3 times for:
    - APIConnectionError (network issues)
    - RateLimitError (rate limit exceeded)

    Does NOT retry for:
    - AuthenticationError (bad API key)
    - InvalidRequestError (malformed request)
    - Other permanent errors

    Args:
        screenshot_base64: Base64-encoded screenshot
        cro_prompt: The CRO analysis prompt
        url: Website URL being analyzed
        page_title: Page title
        deep_info: Whether to use deep analysis mode

    Returns:
        Anthropic message response
    """
    client = get_anthropic_client()
    return client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000 if deep_info else 2000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": screenshot_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"""{cro_prompt}

Website URL: {url}
Page Title: {page_title}

Please analyze this website screenshot and provide your findings in the JSON format specified above.""",
                    },
                ],
            }
        ],
    )
