from typing import List, Optional
from pydantic import BaseModel, HttpUrl


# Models
class CROIssue(BaseModel):
    title: str
    description: str
    why_it_matters: str = ""  # Separate field for "Why It Matters" section
    recommendation: str
    screenshot_base64: Optional[str] = None


class AnalysisRequest(BaseModel):
    url: HttpUrl
    include_screenshots: bool = False
    deep_info: bool = False


class AnalysisResponse(BaseModel):
    url: str
    analyzed_at: str
    issues: List[CROIssue]


# Deep info models
class ExecutiveSummary(BaseModel):
    overview: str
    how_to_act: str


class ScoreDetails(BaseModel):
    score: int
    calculation: str
    rating: str


class ConversionPotential(BaseModel):
    percentage: str
    confidence: str
    rationale: str


class DeepAnalysisResponse(AnalysisResponse):
    total_issues_identified: int
    executive_summary: ExecutiveSummary
    cro_analysis_score: ScoreDetails
    site_performance_score: ScoreDetails
    conversion_rate_increase_potential: ConversionPotential
