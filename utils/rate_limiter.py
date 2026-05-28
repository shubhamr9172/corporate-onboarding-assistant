import os
import logging
from redis import Redis

logger = logging.getLogger("app.rate_limiter")

# Load configuration parameters
MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", 10))
WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", 60))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Redis connection client (Lazy initialized)
_redis_client = None

def get_redis_client():
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = Redis.from_url(REDIS_URL, socket_connect_timeout=2.0)
            # Dry ping
            _redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis is unreachable: {e}. Rate limiting will fail open.")
            _redis_client = False  # Mark as unreachable
    return _redis_client

def is_rate_limited(session_id: str) -> bool:
    """
    Checks if a session_id has exceeded the allowed request limit in the current window.
    Fails open (returns False) if Redis connection is down.
    """
    client = get_redis_client()
    if client is False or client is None:
        # Fail open
        return False
        
    key = f"rate_limit:{session_id}"
    try:
        # Simple fixed window rate limiting
        current_count = client.get(key)
        
        if current_count is None:
            # Set initial value and TTL atomically
            pipe = client.pipeline()
            pipe.set(key, 1, ex=WINDOW_SECONDS)
            pipe.execute()
            return False
            
        count = int(current_count)
        if count >= MAX_REQUESTS:
            logger.warning(f"Session {session_id} rate limited: {count} requests in last {WINDOW_SECONDS}s.")
            return True
            
        # Increment request count
        client.incr(key)
        return False
    except Exception as e:
        logger.error(f"Error checking rate limit in Redis: {e}. Failing open.")
        return False
