"""Production Redis In-Memory Caching and Rate Limiting Service.

Architecture:
- Cache-Aside (Lazy Loading) pattern for expensive LLM reports and frequent database lookups.
- Connection pooling with automatic reconnection.
- Graceful degradation: If Redis is unavailable or unconfigured, the application
  transparently falls back to direct compute/DB queries without raising errors.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from backend.config import settings

logger = logging.getLogger(__name__)

# Global client cache
_redis_client: Any = None
_redis_available: bool | None = None


def get_redis_client() -> Any:
    """Lazily initialize and return a synchronous Redis client with connection pooling."""
    global _redis_client, _redis_available
    if _redis_available is False or not settings.redis_url:
        return None

    if _redis_client is not None:
        return _redis_client

    try:
        import redis

        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            health_check_interval=30,
        )
        # Test connection ping
        _redis_client.ping()
        _redis_available = True
        logger.info("[Redis] Connected successfully to in-memory cache pool at %s", settings.redis_url)
        return _redis_client
    except Exception as exc:
        logger.warning("[Redis] Cache unavailable (%s). Falling back to direct database execution.", exc)
        _redis_available = False
        _redis_client = None
        return None


def generate_cache_key(prefix: str, *args: str) -> str:
    """Generate a standardized, namespaced Redis cache key."""
    sanitized = [str(arg).strip().replace(" ", "_") for arg in args]
    return f"llm_dpeci:{prefix}:{':'.join(sanitized)}"


def get_cached_json(cache_key: str) -> dict[str, Any] | None:
    """Retrieve and deserialize JSON data from Redis cache."""
    client = get_redis_client()
    if client is None:
        return None

    try:
        raw_val = client.get(cache_key)
        if raw_val is not None:
            logger.debug("[Redis CACHE HIT] %s", cache_key)
            return json.loads(raw_val)
        logger.debug("[Redis CACHE MISS] %s", cache_key)
        return None
    except Exception as exc:
        logger.warning("[Redis] Error reading cache key %s: %s", cache_key, exc)
        return None


def set_cached_json(cache_key: str, data: dict[str, Any], ttl_seconds: int | None = None) -> bool:
    """Serialize and write JSON data to Redis with Time-To-Live (TTL)."""
    client = get_redis_client()
    if client is None:
        return False

    ttl = ttl_seconds or settings.redis_cache_ttl_seconds
    try:
        serialized = json.dumps(data)
        client.set(cache_key, serialized, ex=ttl)
        logger.debug("[Redis CACHE SET] %s (TTL: %ss)", cache_key, ttl)
        return True
    except Exception as exc:
        logger.warning("[Redis] Error writing cache key %s: %s", cache_key, exc)
        return False


def invalidate_product_cache(retailer_id: str, product_id: str | None = None) -> int:
    """Invalidate cached reports when a product is re-estimated or data is re-ingested."""
    client = get_redis_client()
    if client is None:
        return 0

    try:
        pattern = f"llm_dpeci:report:{retailer_id}:*"
        if product_id:
            pattern = f"llm_dpeci:report:{retailer_id}:{product_id}:*"

        keys = client.keys(pattern)
        if keys:
            deleted_count = client.delete(*keys)
            logger.info("[Redis INVALIDATE] Cleared %d cached reports matching pattern: %s", deleted_count, pattern)
            return deleted_count
        return 0
    except Exception as exc:
        logger.warning("[Redis] Error invalidating cache pattern %s: %s", pattern, exc)
        return 0


def check_rate_limit(client_identifier: str, endpoint_name: str, max_requests: int = 15, window_seconds: int = 60) -> tuple[bool, int, int]:
    """Sliding rate limiter using Redis atomic counter.
    
    Returns:
        (is_allowed: bool, remaining_requests: int, reset_seconds: int)
    """
    client = get_redis_client()
    if client is None:
        # If Redis is offline, fail-open to preserve API availability
        return True, max_requests, 0

    rate_key = generate_cache_key("ratelimit", endpoint_name, client_identifier)
    try:
        current_count = client.incr(rate_key)
        if current_count == 1:
            client.expire(rate_key, window_seconds)

        ttl = client.ttl(rate_key)
        if current_count > max_requests:
            logger.warning("[Rate Limit EXCEEDED] %s on %s (Count: %d / %d)", client_identifier, endpoint_name, current_count, max_requests)
            return False, 0, max(ttl, 1)

        remaining = max(max_requests - current_count, 0)
        return True, remaining, max(ttl, 1)
    except Exception as exc:
        logger.warning("[Redis] Rate limit check bypassed due to error: %s", exc)
        return True, max_requests, 0
