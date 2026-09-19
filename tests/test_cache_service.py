"""Unit tests for production Redis caching and rate-limiting service."""

from unittest.mock import MagicMock, patch

from backend.services.cache_service import (
    check_rate_limit,
    generate_cache_key,
    get_cached_json,
    invalidate_product_cache,
    set_cached_json,
)


def test_generate_cache_key_standardizes_delimiters() -> None:
    key = generate_cache_key("report", "retailer-123", "prod-456", "abc123hash")
    assert key == "llm_dpeci:report:retailer-123:prod-456:abc123hash"


def test_cache_graceful_degradation_when_redis_offline() -> None:
    # When get_redis_client returns None, cache operations must gracefully return None / False without raising
    with patch("backend.services.cache_service.get_redis_client", return_value=None):
        assert get_cached_json("dummy_key") is None
        assert set_cached_json("dummy_key", {"data": 123}) is False
        assert invalidate_product_cache("retailer-1") == 0
        allowed, remaining, reset = check_rate_limit("127.0.0.1", "test_endpoint")
        assert allowed is True


def test_cache_set_and_get_with_mocked_redis() -> None:
    mock_redis = MagicMock()
    mock_redis.get.return_value = '{"report_type": "gemini_grounded_report", "answer": "Verified price: $18.40"}'

    with patch("backend.services.cache_service.get_redis_client", return_value=mock_redis):
        data = get_cached_json("llm_dpeci:report:test")
        assert data is not None
        assert data["report_type"] == "gemini_grounded_report"
        assert "18.40" in data["answer"]

        success = set_cached_json("llm_dpeci:report:test", {"data": 42}, ttl_seconds=600)
        assert success is True
        mock_redis.set.assert_called_once_with("llm_dpeci:report:test", '{"data": 42}', ex=600)


def test_rate_limiting_enforces_threshold() -> None:
    mock_redis = MagicMock()
    # First call: count = 1 (allowed)
    mock_redis.incr.return_value = 1
    mock_redis.ttl.return_value = 60

    with patch("backend.services.cache_service.get_redis_client", return_value=mock_redis):
        allowed, remaining, reset = check_rate_limit("user-1", "generate_report", max_requests=5, window_seconds=60)
        assert allowed is True
        assert remaining == 4
        assert reset == 60
        mock_redis.expire.assert_called_once()

    # Exceeded call: count = 6 (blocked)
    mock_redis.incr.return_value = 6
    mock_redis.ttl.return_value = 45

    with patch("backend.services.cache_service.get_redis_client", return_value=mock_redis):
        allowed, remaining, reset = check_rate_limit("user-1", "generate_report", max_requests=5, window_seconds=60)
        assert allowed is False
        assert remaining == 0
        assert reset == 45


def test_cache_invalidation_pattern() -> None:
    mock_redis = MagicMock()
    mock_redis.keys.return_value = ["llm_dpeci:report:ret-1:prod-1:hash1", "llm_dpeci:report:ret-1:prod-1:hash2"]
    mock_redis.delete.return_value = 2

    with patch("backend.services.cache_service.get_redis_client", return_value=mock_redis):
        count = invalidate_product_cache("ret-1", "prod-1")
        assert count == 2
        mock_redis.delete.assert_called_once_with(
            "llm_dpeci:report:ret-1:prod-1:hash1",
            "llm_dpeci:report:ret-1:prod-1:hash2",
        )
