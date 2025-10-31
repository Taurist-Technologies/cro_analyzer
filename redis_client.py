"""
Redis client manager for CRO Analyzer
Handles connection pooling, caching, and health checks
"""

import os
import json
import redis
from typing import Optional, Any
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis connection manager with connection pooling and retry logic.
    """

    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        try:
            # Create connection pool for efficiency
            self.pool = redis.ConnectionPool.from_url(
                redis_url,
                max_connections=20,
                decode_responses=True,  # Auto-decode bytes to strings
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )
            self.client = redis.Redis(connection_pool=self.pool)

            # Test connection
            self.client.ping()
            logger.info(f"✅ Redis connected successfully: {redis_url}")
        except redis.ConnectionError as e:
            logger.error(f"❌ Redis connection failed: {str(e)}")
            raise RuntimeError(f"Failed to connect to Redis: {str(e)}")

    def ping(self) -> bool:
        """Check if Redis is available"""
        try:
            return self.client.ping()
        except redis.ConnectionError:
            return False

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Store a value in Redis with optional TTL (Time To Live).

        Args:
            key: Redis key
            value: Value to store (will be JSON-encoded if not a string)
            ttl: Time to live in seconds (None = no expiration)

        Returns:
            True if successful
        """
        try:
            # JSON encode if not a string
            if not isinstance(value, str):
                value = json.dumps(value)

            if ttl:
                return self.client.setex(key, ttl, value)
            else:
                return self.client.set(key, value)
        except Exception as e:
            logger.error(f"Redis SET failed for key '{key}': {str(e)}")
            return False

    def get(self, key: str, decode_json: bool = True) -> Optional[Any]:
        """
        Retrieve a value from Redis.

        Args:
            key: Redis key
            decode_json: If True, attempt to JSON-decode the value

        Returns:
            Value if found, None otherwise
        """
        try:
            value = self.client.get(key)

            if value is None:
                return None

            # Attempt JSON decode if requested
            if decode_json:
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # Not JSON, return as-is
                    return value

            return value
        except Exception as e:
            logger.error(f"Redis GET failed for key '{key}': {str(e)}")
            return None

    def delete(self, key: str) -> bool:
        """Delete a key from Redis"""
        try:
            return bool(self.client.delete(key))
        except Exception as e:
            logger.error(f"Redis DELETE failed for key '{key}': {str(e)}")
            return False

    def exists(self, key: str) -> bool:
        """Check if a key exists in Redis"""
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger.error(f"Redis EXISTS failed for key '{key}': {str(e)}")
            return False

    def set_hash(self, name: str, mapping: dict, ttl: Optional[int] = None) -> bool:
        """
        Store a hash (dictionary) in Redis.

        Args:
            name: Hash name
            mapping: Dictionary to store
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        try:
            # JSON encode all values in the mapping
            encoded_mapping = {
                k: json.dumps(v) if not isinstance(v, str) else v
                for k, v in mapping.items()
            }

            result = self.client.hset(name, mapping=encoded_mapping)

            if ttl:
                self.client.expire(name, ttl)

            return True
        except Exception as e:
            logger.error(f"Redis HSET failed for hash '{name}': {str(e)}")
            return False

    def get_hash(self, name: str, decode_json: bool = True) -> Optional[dict]:
        """
        Retrieve a hash from Redis.

        Args:
            name: Hash name
            decode_json: If True, attempt to JSON-decode values

        Returns:
            Dictionary if found, None otherwise
        """
        try:
            result = self.client.hgetall(name)

            if not result:
                return None

            # Decode JSON values if requested
            if decode_json:
                decoded = {}
                for k, v in result.items():
                    try:
                        decoded[k] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        decoded[k] = v
                return decoded

            return result
        except Exception as e:
            logger.error(f"Redis HGETALL failed for hash '{name}': {str(e)}")
            return None

    def cache_analysis(
        self,
        url: str,
        analysis_result: dict,
        ttl: int = 86400
    ) -> bool:
        """
        Cache an analysis result for a URL.

        Args:
            url: Website URL
            analysis_result: Complete analysis result dictionary
            ttl: Time to live in seconds (default: 24 hours)

        Returns:
            True if cached successfully
        """
        cache_key = f"cache:analysis:{url}"
        return self.set(cache_key, analysis_result, ttl=ttl)

    def get_cached_analysis(self, url: str) -> Optional[dict]:
        """
        Retrieve cached analysis result for a URL.

        Args:
            url: Website URL

        Returns:
            Cached analysis result if found, None otherwise
        """
        cache_key = f"cache:analysis:{url}"
        return self.get(cache_key, decode_json=True)

    def clear_cache(self, pattern: str = "cache:*") -> int:
        """
        Clear cached entries matching a pattern.

        Args:
            pattern: Redis key pattern (default: all cache entries)

        Returns:
            Number of keys deleted
        """
        try:
            keys = self.client.keys(pattern)
            if keys:
                return self.client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis cache clear failed for pattern '{pattern}': {str(e)}")
            return 0

    def get_stats(self) -> dict:
        """
        Get Redis connection and memory stats.

        Returns:
            Dictionary with Redis statistics
        """
        try:
            info = self.client.info()
            return {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace": info.get("keyspace", {}),
            }
        except Exception as e:
            logger.error(f"Failed to get Redis stats: {str(e)}")
            return {"error": str(e)}

    def close(self):
        """Close Redis connection pool"""
        try:
            self.pool.disconnect()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {str(e)}")


# Global Redis client instance
redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """
    Get or create the global Redis client instance.

    Returns:
        RedisClient instance
    """
    global redis_client

    if redis_client is None:
        redis_client = RedisClient()

    return redis_client


def close_redis_client():
    """Close the global Redis client"""
    global redis_client

    if redis_client is not None:
        redis_client.close()
        redis_client = None
