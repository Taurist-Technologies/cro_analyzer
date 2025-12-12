"""
Validation Package for CRO Analyzer

This package provides post-analysis validation to filter out false positive
CRO recommendations by verifying elements actually exist on the page.

Modules:
- recommendation_validator: Playwright-based validation of recommendations
- ai_validator: AI-based validation for uncertain/subjective cases
"""

from .recommendation_validator import RecommendationValidator
from .ai_validator import AIValidator

__all__ = ["RecommendationValidator", "AIValidator"]
