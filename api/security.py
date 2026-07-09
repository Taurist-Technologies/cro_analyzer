"""
Security dependencies for analysis endpoints: API-key auth and a simple
Redis-backed per-IP rate limit. Both are configured via environment
(API_AUTH_KEY, RATE_LIMIT_PER_MINUTE) so local development works with
neither enabled.
"""

import hmac
import logging
import time

from fastapi import Header, HTTPException, Request

from config import settings

logger = logging.getLogger(__name__)


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Enforce X-API-Key when API_AUTH_KEY is configured."""
    if not settings.API_AUTH_KEY:
        return
    if not hmac.compare_digest(x_api_key, settings.API_AUTH_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def enforce_rate_limit(request: Request) -> None:
    """
    Fixed-window per-IP limit on analysis submissions. Fails open when Redis
    is unavailable — availability beats strictness for a marketing tool.
    """
    limit = settings.RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return

    client_ip = _client_ip(request)
    window = int(time.time() // 60)
    key = f"ratelimit:{client_ip}:{window}"

    try:
        from core.cache import get_redis_client

        client = get_redis_client().client
        count = client.incr(key)
        if count == 1:
            client.expire(key, 90)
        if count > limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({limit} analyses per minute). Please wait a moment.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Rate limiter unavailable (allowing request): {e}")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
