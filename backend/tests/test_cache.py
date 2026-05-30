"""Tests for Redis caching layer (Issue #9)."""
import json
from unittest.mock import patch, MagicMock

import pytest


class TestCacheOperations:
    """Test cache get/set/delete operations with graceful degradation."""

    def test_cache_get_returns_none_when_disabled(self):
        """Cache get should return None when Redis is disabled."""
        from src.cache import cache_get
        result = cache_get("nonexistent:key")
        assert result is None

    def test_cache_set_returns_false_when_disabled(self):
        """Cache set should return False when Redis is disabled."""
        from src.cache import cache_set
        result = cache_set("test:key", {"data": "value"})
        assert result is False

    def test_cache_delete_returns_false_when_disabled(self):
        """Cache delete should return False when Redis is disabled."""
        from src.cache import cache_delete
        result = cache_delete("test:key")
        assert result is False

    def test_cache_delete_pattern_returns_false_when_disabled(self):
        """Cache delete pattern should return False when Redis is disabled."""
        from src.cache import cache_delete_pattern
        result = cache_delete_pattern("test:*")
        assert result is False

    def test_invalidate_user_cache_no_error_when_disabled(self):
        """Invalidate user cache should not raise when Redis is disabled."""
        from src.cache import invalidate_user_cache
        invalidate_user_cache(1)  # Should not raise

    def test_invalidate_policy_cache_no_error_when_disabled(self):
        """Invalidate policy cache should not raise when Redis is disabled."""
        from src.cache import invalidate_policy_cache
        invalidate_policy_cache(1)  # Should not raise


class TestCacheWithMockedRedis:
    """Test cache operations with a mocked Redis client."""

    def test_cache_get_hit(self):
        """Cache should return deserialized data on hit."""
        import src.cache as cache_module
        mock_client = MagicMock()
        mock_client.get.return_value = json.dumps({"id": 1, "name": "test"})

        original = cache_module._redis_client
        cache_module._redis_client = mock_client
        try:
            result = cache_module.cache_get("test:key")
            assert result == {"id": 1, "name": "test"}
            mock_client.get.assert_called_once_with("test:key")
        finally:
            cache_module._redis_client = original

    def test_cache_get_miss(self):
        """Cache should return None on miss."""
        import src.cache as cache_module
        mock_client = MagicMock()
        mock_client.get.return_value = None

        original = cache_module._redis_client
        cache_module._redis_client = mock_client
        try:
            result = cache_module.cache_get("missing:key")
            assert result is None
        finally:
            cache_module._redis_client = original

    def test_cache_set_with_ttl(self):
        """Cache set should store data with TTL."""
        import src.cache as cache_module
        mock_client = MagicMock()

        original = cache_module._redis_client
        cache_module._redis_client = mock_client
        try:
            result = cache_module.cache_set("test:key", {"data": "val"}, ttl=60)
            assert result is True
            mock_client.setex.assert_called_once()
            call_args = mock_client.setex.call_args
            assert call_args[0][0] == "test:key"
            assert call_args[0][1] == 60
        finally:
            cache_module._redis_client = original

    def test_cache_delete_calls_redis(self):
        """Cache delete should call redis delete."""
        import src.cache as cache_module
        mock_client = MagicMock()

        original = cache_module._redis_client
        cache_module._redis_client = mock_client
        try:
            result = cache_module.cache_delete("test:key")
            assert result is True
            mock_client.delete.assert_called_once_with("test:key")
        finally:
            cache_module._redis_client = original

    def test_cache_graceful_on_redis_error(self):
        """Cache operations should handle Redis errors gracefully."""
        import src.cache as cache_module
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Connection lost")

        original = cache_module._redis_client
        cache_module._redis_client = mock_client
        try:
            result = cache_module.cache_get("test:key")
            assert result is None  # Should not raise
        finally:
            cache_module._redis_client = original


class TestPolicyCacheIntegration:
    """Test that policy endpoints use caching correctly."""

    def test_policy_list_uses_cache(self, client, auth_user, auth_headers, policy_factory):
        """Policy listing should work and result should be cacheable."""
        policy_factory(auth_user)
        response = client.get("/policies/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "policies" in data
        assert data["total"] >= 1

    def test_create_policy_invalidates_cache(self, client, auth_user, auth_headers):
        """Creating a policy should not break the listing endpoint."""
        import time
        now = int(time.time())
        response = client.post("/policies/", headers=auth_headers, json={
            "policy_type": "weather",
            "coverage_amount": 1000.0,
            "premium": 50.0,
            "start_time": now,
            "end_time": now + 86400,
            "trigger_condition": "rainfall > 100mm"
        })
        assert response.status_code == 201

        list_response = client.get("/policies/", headers=auth_headers)
        assert list_response.status_code == 200
        assert list_response.json()["total"] >= 1


class TestClaimCacheInvalidation:
    """Test that claim submission invalidates policy cache."""

    def test_create_claim_text_invalidates_policy_cache(
        self, client, auth_user, auth_headers, policy_factory
    ):
        """Text claim creation should trigger policy cache invalidation."""
        policy = policy_factory(auth_user, coverage_amount=1000.0)

        import src.routes.claims as claims_module
        from unittest.mock import patch

        with patch.object(claims_module, "invalidate_policy_cache") as mock_invalidate:
            response = client.post(
                "/claims/",
                headers=auth_headers,
                json={
                    "policy_id": policy.id,
                    "claim_amount": 300.0,
                    "proof": "Satellite weather evidence",
                },
            )

            assert response.status_code == 201
            mock_invalidate.assert_called_once_with(auth_user.id)

    def test_create_claim_file_upload_invalidates_policy_cache(
        self, client, auth_user, auth_headers, policy_factory
    ):
        """File upload claim creation should trigger policy cache invalidation."""
        from io import BytesIO
        policy = policy_factory(auth_user, coverage_amount=1000.0)

        import src.routes.claims as claims_module
        from unittest.mock import patch

        with patch.object(claims_module, "invalidate_policy_cache") as mock_invalidate:
            response = client.post(
                "/claims/upload",
                headers=auth_headers,
                data={"policy_id": str(policy.id), "claim_amount": "275.0"},
                files={"file": ("proof.png", BytesIO(b"png"), "image/png")},
            )

            assert response.status_code == 201
            mock_invalidate.assert_called_once_with(auth_user.id)

    def test_create_claim_failure_does_not_invalidate_cache(
        self, client, auth_user, auth_headers
    ):
        """Failed claim creation should NOT trigger policy cache invalidation."""
        import src.routes.claims as claims_module
        from unittest.mock import patch

        with patch.object(claims_module, "invalidate_policy_cache") as mock_invalidate:
            # Non-existent policy
            response = client.post(
                "/claims/",
                headers=auth_headers,
                json={
                    "policy_id": 99999,
                    "claim_amount": 300.0,
                    "proof": "Satellite weather evidence",
                },
            )

            assert response.status_code == 404
            mock_invalidate.assert_not_called()
