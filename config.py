"""
Centralized configuration for CRO Analyzer
All environment variables and settings are defined here
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Provides centralized configuration with validation and defaults.
    """

    # ======================
    # API Configuration
    # ======================
    ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API key")
    ANTHROPIC_MODEL: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model to use for analysis"
    )
    MAX_TOKENS: int = Field(default=4000, description="Max tokens for Claude response")

    # ======================
    # Redis Configuration
    # ======================
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )

    # ======================
    # Celery Configuration
    # ======================
    CELERY_BROKER_URL: Optional[str] = Field(
        default=None,
        description="Celery broker URL (defaults to REDIS_URL if not set)"
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/1",
        description="Celery result backend URL"
    )
    CELERY_RESULT_EXPIRES: int = Field(
        default=259200,  # 72 hours (3 days)
        description="Time in seconds before task results expire"
    )
    CELERY_WORKER_CONCURRENCY: int = Field(
        default=5,
        description="Number of concurrent Celery workers"
    )

    # ======================
    # Browser Pool Configuration
    # ======================
    BROWSER_POOL_SIZE: int = Field(
        default=5,
        description="Number of browser instances in pool"
    )
    BROWSER_MAX_PAGES: int = Field(
        default=10,
        description="Max pages per browser before recycling"
    )
    BROWSER_TIMEOUT: int = Field(
        default=180,
        description="Max browser age in seconds before recycling"
    )
    BROWSER_CLOSE_TIMEOUT: int = Field(
        default=10,
        description="Timeout for closing browser in seconds"
    )
    BROWSER_LAUNCH_TIMEOUT: int = Field(
        default=20,
        description="Timeout for launching browser in seconds"
    )

    # ======================
    # Cache Configuration
    # ======================
    CACHE_TTL: int = Field(
        default=86400,  # 24 hours
        description="Cache time-to-live in seconds"
    )

    # ======================
    # Task Configuration
    # ======================
    TASK_TIME_LIMIT: int = Field(
        default=720,  # 12 minutes
        description="Hard time limit for tasks in seconds"
    )
    TASK_SOFT_TIME_LIMIT: int = Field(
        default=600,  # 10 minutes
        description="Soft time limit for tasks in seconds"
    )
    TASK_DEFAULT_RETRY_DELAY: int = Field(
        default=60,
        description="Default delay before task retry in seconds"
    )
    TASK_MAX_RETRIES: int = Field(
        default=3,
        description="Maximum number of task retries"
    )

    # ======================
    # Worker Configuration
    # ======================
    WORKER_MODE: bool = Field(
        default=False,
        description="Set to True for worker containers"
    )
    API_WORKERS: int = Field(
        default=2,
        description="Number of Uvicorn workers for API"
    )
    WORKER_PREFETCH_MULTIPLIER: int = Field(
        default=1,
        description="Tasks to prefetch per worker"
    )
    WORKER_MAX_TASKS_PER_CHILD: int = Field(
        default=10,
        description="Max tasks before worker restart"
    )

    # ======================
    # Screenshot Configuration
    # ======================
    MAX_SCREENSHOT_DIMENSION: int = Field(
        default=1800,
        description="Maximum screenshot dimension in pixels"
    )
    VIEWPORT_WIDTH: int = Field(
        default=1920,
        description="Browser viewport width"
    )
    VIEWPORT_HEIGHT: int = Field(
        default=1080,
        description="Browser viewport height"
    )

    # ======================
    # Logging Configuration
    # ======================
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level"
    )

    @property
    def celery_broker(self) -> str:
        """Get Celery broker URL, defaulting to REDIS_URL if not set"""
        return self.CELERY_BROKER_URL or self.REDIS_URL

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Allow extra env vars in .env file


# Global settings instance
settings = Settings()


# ======================
# Convenience Functions
# ======================

def get_redis_url() -> str:
    """Get Redis connection URL"""
    return settings.REDIS_URL


def get_celery_broker_url() -> str:
    """Get Celery broker URL"""
    return settings.celery_broker


def get_celery_result_backend() -> str:
    """Get Celery result backend URL"""
    return settings.CELERY_RESULT_BACKEND


def get_anthropic_api_key() -> str:
    """Get Anthropic API key"""
    return settings.ANTHROPIC_API_KEY


def get_anthropic_model() -> str:
    """Get Anthropic model name"""
    return settings.ANTHROPIC_MODEL


def is_worker_mode() -> bool:
    """Check if running in worker mode"""
    return settings.WORKER_MODE
