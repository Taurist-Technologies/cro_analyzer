"""
AI Validator Module for CRO Analyzer

Uses Claude to validate uncertain CRO recommendations that Playwright
cannot definitively verify (visual issues, subjective claims, etc.).

This is Layer 3 of the validation pipeline:
1. Pre-analysis detection (ElementDetector) - prevents false positives
2. Playwright post-validation (RecommendationValidator) - catches remaining false positives
3. AI POST-VALIDATION (this module) - handles uncertain/subjective cases
"""

from typing import Dict, List, Any, Optional, Tuple
from playwright.async_api import Page
import anthropic
import base64
import logging
import json
import re

logger = logging.getLogger(__name__)


class AIValidator:
    """
    Uses Claude to validate uncertain CRO recommendations.

    For recommendations that Playwright cannot definitively verify:
    - Visual/design issues
    - Subjective UX claims
    - Complex multi-element interactions
    - Elements hidden behind JavaScript interactions
    """

    # Section-to-viewport-area mapping for focused screenshots
    SECTION_AREAS = {
        "hero": {"desktop": {"x": 0, "y": 0, "width": 1920, "height": 900}},
        "header": {"desktop": {"x": 0, "y": 0, "width": 1920, "height": 150}},
        "navigation": {"desktop": {"x": 0, "y": 0, "width": 1920, "height": 200}},
        "above_fold": {"desktop": {"x": 0, "y": 0, "width": 1920, "height": 1080}},
        "footer": {"desktop": {"x": 0, "y": "bottom", "width": 1920, "height": 400}},
        "sidebar": {"desktop": {"x": 0, "y": 200, "width": 400, "height": 600}},
        "cta": {"desktop": {"x": 0, "y": 0, "width": 1920, "height": 1080}},
        "product": {"desktop": {"x": 0, "y": 0, "width": 1920, "height": 1200}},
        "form": {"desktop": {"x": 0, "y": 0, "width": 1920, "height": 1080}},
    }

    # Validation prompt template
    VALIDATION_PROMPT = """I need you to verify if this CRO (Conversion Rate Optimization) issue actually exists on the page shown in the screenshot.

**ISSUE TO VERIFY:**
- Title: {title}
- Description: {description}
- Recommendations: {recommendations}

**YOUR TASK:**
Look carefully at the screenshot and determine if this issue actually exists.

**CRITICAL FOR "VALUE PROPOSITION" OR "CLARITY" CLAIMS:**
If the issue claims something "lacks clear value proposition", "doesn't clearly communicate", "generic", or similar:
1. Look for ANY text that explains benefits, value, or what users will receive
2. Newsletter/signup forms often have benefit text NEAR the form (above, below, or beside it)
3. Popup modals frequently include value messaging in headers or subtext
4. If benefits ARE visible ANYWHERE in the relevant area, the issue is FALSE
5. Examples of valid value propositions:
   - "Get VIP access to sales"
   - "Early access to new products"
   - "Exclusive offers and discounts"
   - "Join X members" (social proof as value)
   - Any bullet points listing what subscribers receive

**IMPORTANT CONSIDERATIONS:**
1. Elements may be present but styled differently than expected
2. Mobile hamburger menus may appear as three horizontal lines (≡) or dots
3. Star ratings may use filled/empty icons, numbers, or percentage bars
4. Trust badges may be logos, icons, or text-based
5. Social proof can be testimonials, reviews, logos, or customer counts
6. Value propositions may be in smaller text, subheadings, or bullet points

**BE SKEPTICAL OF "LACKS CLARITY" CLAIMS:**
Before confirming such an issue exists, actively search the screenshot for ANY relevant text that contradicts the claim. If you find clear value messaging, the issue does NOT exist.

**RESPOND IN THIS EXACT JSON FORMAT:**
{{
    "exists": true/false,
    "confidence": "HIGH" / "MEDIUM" / "LOW",
    "explanation": "Brief explanation with SPECIFIC text/evidence from the screenshot that supports or contradicts the issue",
    "elements_found": ["List any relevant elements you DO see that relate to or contradict this issue"]
}}

Only respond with the JSON object, no additional text."""

    def __init__(self, client: anthropic.Anthropic):
        """
        Initialize the AI validator.

        Args:
            client: Anthropic client instance
        """
        self.client = client

    async def validate_uncertain_issues(
        self,
        page: Page,
        issues: List[Dict[str, Any]],
        model: str = "claude-sonnet-4-20250514"
    ) -> List[Dict[str, Any]]:
        """
        Validate a list of uncertain issues using AI.

        Args:
            page: Playwright Page object
            issues: List of issue dictionaries that need AI validation
            model: Claude model to use for validation

        Returns:
            List of issues with updated validation status
        """
        if not issues:
            return issues

        logger.info(f"🤖 AI validating {len(issues)} uncertain issues")

        validated = []
        for issue in issues:
            validation = await self.validate_issue(page, issue, model)
            issue["validation"] = validation
            validated.append(issue)

            if validation.get("should_filter", False):
                logger.info(
                    f"❌ AI filtered: '{issue.get('title', 'Unknown')}' - "
                    f"{validation.get('explanation', 'No explanation')}"
                )
            else:
                logger.debug(
                    f"✅ AI verified: '{issue.get('title', 'Unknown')}'"
                )

        filtered_count = sum(1 for i in validated if i.get("validation", {}).get("should_filter"))
        logger.info(f"🤖 AI validation complete: {len(validated) - filtered_count} kept, {filtered_count} filtered")

        return validated

    async def validate_issue(
        self,
        page: Page,
        issue: Dict[str, Any],
        model: str = "claude-sonnet-4-20250514"
    ) -> Dict[str, Any]:
        """
        Validate a single issue using AI analysis of a focused screenshot.

        Args:
            page: Playwright Page object
            issue: Issue dictionary with title, description, recommendations
            model: Claude model to use

        Returns:
            Validation result dictionary
        """
        try:
            # Get the section mentioned in the issue
            section = issue.get("section", "above_fold")

            # Capture focused screenshot
            screenshot_base64 = await self._capture_focused_screenshot(page, section)

            if not screenshot_base64:
                return {
                    "status": "error",
                    "reason": "Failed to capture screenshot for validation",
                    "should_filter": False,
                    "ai_validated": True,
                }

            # Build the validation prompt
            title = issue.get("title", "")
            description = issue.get("description", "")
            recommendations = issue.get("recommendations", [])
            if isinstance(recommendations, list):
                recommendations_text = "\n".join(f"- {r}" for r in recommendations)
            else:
                recommendations_text = str(recommendations)

            prompt = self.VALIDATION_PROMPT.format(
                title=title,
                description=description,
                recommendations=recommendations_text
            )

            # Call Claude for validation
            response = self.client.messages.create(
                model=model,
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }]
            )

            # Parse the response
            return self._parse_validation_response(response)

        except Exception as e:
            logger.error(f"AI validation error: {e}")
            return {
                "status": "error",
                "reason": f"AI validation failed: {str(e)}",
                "should_filter": False,
                "ai_validated": True,
            }

    async def _capture_focused_screenshot(
        self,
        page: Page,
        section: str
    ) -> Optional[str]:
        """
        Capture a focused screenshot of a specific section.

        Args:
            page: Playwright Page object
            section: Section name (hero, header, footer, etc.)

        Returns:
            Base64-encoded screenshot or None on failure
        """
        try:
            # For now, capture the full viewport
            # In the future, we could scroll to specific sections
            screenshot_bytes = await page.screenshot(
                full_page=False,  # Just the viewport for focused analysis
                type="png"
            )

            return base64.b64encode(screenshot_bytes).decode("utf-8")

        except Exception as e:
            logger.error(f"Screenshot capture error: {e}")
            return None

    def _parse_validation_response(
        self,
        response: anthropic.types.Message
    ) -> Dict[str, Any]:
        """
        Parse Claude's validation response.

        Args:
            response: Claude API response

        Returns:
            Parsed validation result
        """
        try:
            # Extract text content
            text_content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text_content += block.text

            # Try to parse JSON from the response
            json_match = re.search(r'\{[\s\S]*\}', text_content)
            if json_match:
                result = json.loads(json_match.group())

                exists = result.get("exists", True)
                confidence = result.get("confidence", "LOW")
                explanation = result.get("explanation", "")
                elements_found = result.get("elements_found", [])

                # Determine if we should filter based on AI response
                # Filter if issue does NOT exist AND confidence is HIGH
                should_filter = not exists and confidence == "HIGH"

                return {
                    "status": "ai_validated",
                    "exists": exists,
                    "confidence": confidence,
                    "explanation": explanation,
                    "elements_found": elements_found,
                    "should_filter": should_filter,
                    "ai_validated": True,
                    "reason": explanation if should_filter else "Issue verified by AI",
                }

            # If we couldn't parse JSON, don't filter (be conservative)
            return {
                "status": "parse_error",
                "reason": "Could not parse AI validation response",
                "raw_response": text_content[:500],
                "should_filter": False,
                "ai_validated": True,
            }

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in AI validation: {e}")
            return {
                "status": "parse_error",
                "reason": f"JSON parse error: {str(e)}",
                "should_filter": False,
                "ai_validated": True,
            }
        except Exception as e:
            logger.error(f"Error parsing AI validation response: {e}")
            return {
                "status": "error",
                "reason": f"Parse error: {str(e)}",
                "should_filter": False,
                "ai_validated": True,
            }


async def ai_validate_uncertain_issues(
    client: anthropic.Anthropic,
    page: Page,
    issues: List[Dict[str, Any]],
    model: str = "claude-sonnet-4-20250514"
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Helper function to AI validate uncertain issues.

    Args:
        client: Anthropic client
        page: Playwright Page object
        issues: Issues marked as needing AI validation
        model: Claude model to use

    Returns:
        Tuple of (validated_issues, filtered_issues, stats)
    """
    from typing import Tuple

    if not issues:
        return [], [], {"ai_validated": 0, "ai_filtered": 0}

    validator = AIValidator(client)
    validated = await validator.validate_uncertain_issues(page, issues, model)

    kept = [i for i in validated if not i.get("validation", {}).get("should_filter")]
    filtered = [i for i in validated if i.get("validation", {}).get("should_filter")]

    stats = {
        "ai_validated": len(validated),
        "ai_kept": len(kept),
        "ai_filtered": len(filtered),
    }

    return kept, filtered, stats
