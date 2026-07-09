"""
Centralized configuration for CRO Analyzer.
All environment variables and settings are defined here.
"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ======================
    # Anthropic API
    # ======================
    ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API key")
    ANTHROPIC_MODEL: str = Field(
        default="claude-opus-4-8",
        description="Claude model used for PDP analysis",
    )
    MAX_TOKENS: int = Field(default=8000, description="Max tokens for Claude response")

    # ======================
    # API security
    # ======================
    API_AUTH_KEY: str = Field(
        default="",
        description="If set, analyze endpoints require this value in the X-API-Key header",
    )
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=10,
        description="Max analysis submissions per client IP per minute (0 disables)",
    )

    # ======================
    # Redis / Celery
    # ======================
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_BROKER_URL: Optional[str] = Field(default=None)
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_EXPIRES: int = Field(default=259200, description="72h result retention")
    CELERY_WORKER_CONCURRENCY: int = Field(default=5)

    # ======================
    # Analysis time budget
    # ======================
    ANALYSIS_TIMEOUT: int = Field(
        default=150,
        description="Per-attempt budget for one full analysis in seconds",
    )
    NAV_TIMEOUT_MS: int = Field(
        default=45000,
        description="Playwright navigation timeout (domcontentloaded) in ms",
    )
    TASK_TIME_LIMIT: int = Field(
        default=360, description="Celery hard time limit (covers 2 attempts + overhead)"
    )
    TASK_SOFT_TIME_LIMIT: int = Field(default=330)
    TASK_DEFAULT_RETRY_DELAY: int = Field(default=2)
    TASK_MAX_RETRIES: int = Field(default=1)

    # ======================
    # Browser runtime
    # ======================
    BROWSER_MAX_USES: int = Field(
        default=20, description="Analyses per browser before recycling"
    )
    BROWSER_MAX_AGE_SECONDS: int = Field(
        default=1800, description="Max browser age before recycling"
    )
    BROWSER_CLOSE_TIMEOUT: int = Field(default=10)
    BROWSER_LAUNCH_TIMEOUT: int = Field(default=30)

    # ======================
    # Cache / workers / misc
    # ======================
    CACHE_TTL: int = Field(default=86400, description="Analysis cache TTL (24h)")
    WORKER_MODE: bool = Field(default=False)
    API_WORKERS: int = Field(default=2)
    WORKER_PREFETCH_MULTIPLIER: int = Field(default=1)
    WORKER_MAX_TASKS_PER_CHILD: int = Field(default=50)
    LOG_LEVEL: str = Field(default="INFO")

    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
