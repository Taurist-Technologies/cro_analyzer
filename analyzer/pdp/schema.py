"""
JSON schema for the structured PDP analysis output.

Passed to the Anthropic API via output_config.format so the response is
schema-validated server-side — no post-hoc JSON repair needed.

Structured-output limitations to keep in mind when editing:
- no minItems/maxItems (the "exactly 5 quick wins" rule lives in the prompt
  and is enforced again in analysis.py)
- every object needs additionalProperties: false and a full required list
"""

_SCORECARD = {
    "type": "object",
    "additionalProperties": False,
    "required": ["score", "color", "rationale"],
    "properties": {
        "score": {"type": "integer"},
        "color": {"type": "string", "enum": ["red", "yellow", "green"]},
        "rationale": {"type": "string"},
    },
}

QUICK_WIN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "title",
        "element",
        "viewport",
        "whats_wrong",
        "why_it_matters",
        "recommendations",
        "suggested_copy",
        "impact",
        "effort",
        "priority_score",
        "priority_rationale",
        "grounding",
        "grounding_source",
    ],
    "properties": {
        "title": {"type": "string"},
        "element": {
            "type": "string",
            "description": "The specific PDP element the finding is about, e.g. 'Add-to-cart button', 'Product gallery', 'Reviews section'",
        },
        "viewport": {"type": "string", "enum": ["desktop", "mobile", "both"]},
        "whats_wrong": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "suggested_copy": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "Concrete replacement copy when the fix involves wording (CTA text, headline, shipping line). Null when not applicable.",
        },
        "impact": {"type": "string", "enum": ["high", "medium", "low"]},
        "effort": {"type": "string", "enum": ["low", "medium", "high"]},
        "priority_score": {"type": "integer"},
        "priority_rationale": {"type": "string"},
        "grounding": {
            "type": "string",
            "enum": ["proprietary_audit", "knowledge_base", "expert_practice"],
            "description": "Which knowledge tier this finding is rooted in (chain of command)",
        },
        "grounding_source": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "Client name for proprietary_audit, pattern title for knowledge_base, null for expert_practice",
        },
    },
}

PDP_ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "executive_summary",
        "quick_wins",
        "scorecards",
        "conversion_rate_increase_potential",
        "total_issues_identified",
    ],
    "properties": {
        "executive_summary": {
            "type": "object",
            "additionalProperties": False,
            "required": ["overview", "how_to_act"],
            "properties": {
                "overview": {"type": "string"},
                "how_to_act": {"type": "string"},
            },
        },
        "quick_wins": {"type": "array", "items": QUICK_WIN_SCHEMA},
        "scorecards": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "buy_box",
                "product_content",
                "social_proof",
                "mobile_experience",
                "page_speed",
            ],
            "properties": {
                "buy_box": _SCORECARD,
                "product_content": _SCORECARD,
                "social_proof": _SCORECARD,
                "mobile_experience": _SCORECARD,
                "page_speed": _SCORECARD,
            },
        },
        "conversion_rate_increase_potential": {
            "type": "object",
            "additionalProperties": False,
            "required": ["percentage", "confidence", "rationale"],
            "properties": {
                "percentage": {"type": "string"},
                "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
                "rationale": {"type": "string"},
            },
        },
        "total_issues_identified": {"type": "integer"},
    },
}
