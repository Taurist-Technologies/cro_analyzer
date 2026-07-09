"""
Pydantic models for CRO Analyzer API — PDP-focused analysis shapes.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, HttpUrl


class AnalysisRequest(BaseModel):
    url: HttpUrl
    include_screenshots: bool = False


class QuickWin(BaseModel):
    title: str
    element: str = ""
    viewport: str = "both"
    whats_wrong: str = ""
    why_it_matters: str = ""
    recommendations: List[str] = []
    suggested_copy: Optional[str] = None
    impact: str = "medium"
    effort: str = "medium"
    priority_score: int = 0
    priority_rationale: str = ""


class Scorecard(BaseModel):
    score: int = 0
    color: str = "yellow"
    rationale: str = ""


class ExecutiveSummary(BaseModel):
    overview: str = ""
    how_to_act: str = ""


class ConversionPotential(BaseModel):
    percentage: str = ""
    confidence: str = "Medium"
    rationale: str = ""


class PDPAnalysisResponse(BaseModel):
    status: str
    url: str
    analyzed_at: str
    page_title: str = ""
    message: Optional[str] = None  # populated for not_product_page
    page_type_signals: List[str] = []
    total_issues_identified: int = 0
    issues: List[QuickWin] = []
    scorecards: Dict[str, Scorecard] = {}
    executive_summary: Optional[ExecutiveSummary] = None
    conversion_rate_increase_potential: Optional[ConversionPotential] = None
    product: Dict = {}
    performance: Dict = {}
    add_to_cart_test: Dict = {}
    analysis_duration_seconds: Optional[float] = None
    screenshots: Optional[Dict[str, Optional[str]]] = None
    screenshots_url: Optional[str] = None
