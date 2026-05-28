import pytest
from unittest.mock import MagicMock, patch
import utils.rate_limiter as rate_limiter

def test_rate_limiter_fail_open_when_redis_down():
    # Force get_redis_client to return False (unreachable)
    with patch("utils.rate_limiter.get_redis_client", return_value=False):
        # Should fail open and return False (not limited)
        assert rate_limiter.is_rate_limited("session_xyz") is False

def test_rate_limiter_new_session():
    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # Key doesn't exist
    
    mock_pipeline = MagicMock()
    mock_redis.pipeline.return_value = mock_pipeline
    
    with patch("utils.rate_limiter.get_redis_client", return_value=mock_redis):
        # Should return False (not limited) and initialize the key in Redis
        assert rate_limiter.is_rate_limited("session_123") is False
        mock_redis.get.assert_called_with("rate_limit:session_123")
        mock_redis.pipeline.assert_called_once()
        mock_pipeline.set.assert_called_with("rate_limit:session_123", 1, ex=rate_limiter.WINDOW_SECONDS)
        mock_pipeline.execute.assert_called_once()

def test_rate_limiter_under_limit():
    mock_redis = MagicMock()
    # Mock current count as 5, which is less than MAX_REQUESTS (default 10)
    mock_redis.get.return_value = b"5"
    
    with patch("utils.rate_limiter.get_redis_client", return_value=mock_redis):
        # Should return False and increment the count
        assert rate_limiter.is_rate_limited("session_123") is False
        mock_redis.incr.assert_called_with("rate_limit:session_123")

def test_rate_limiter_over_limit():
    mock_redis = MagicMock()
    # Mock current count as 10 (equal to MAX_REQUESTS)
    mock_redis.get.return_value = b"10"
    
    with patch("utils.rate_limiter.get_redis_client", return_value=mock_redis):
        # Should return True (limited) and NOT increment the count
        assert rate_limiter.is_rate_limited("session_123") is True
        mock_redis.incr.assert_not_called()

def test_rate_limiter_exception_fails_open():
    mock_redis = MagicMock()
    mock_redis.get.side_effect = Exception("Redis connection error")
    
    with patch("utils.rate_limiter.get_redis_client", return_value=mock_redis):
        # Exception during get should log and fail open (return False)
        assert rate_limiter.is_rate_limited("session_123") is False
