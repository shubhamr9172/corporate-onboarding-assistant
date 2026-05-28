import os
import sys
import logging
from dotenv import load_dotenv

# Set up logging for config check
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def check_configuration() -> bool:
    """
    Validates essential environment variables and connections on startup.
    Fails fast (returns False/exits) if critical configurations are missing.
    """
    # Load env variables from .env
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dotenv_path = os.path.join(root_dir, ".env")
    load_dotenv(dotenv_path=dotenv_path)
    
    errors = []
    
    # 1. Validate GOOGLE_API_KEY
    google_key = os.getenv("GOOGLE_API_KEY")
    if not google_key:
        errors.append("MISSING: GOOGLE_API_KEY environment variable is not set.")
    elif len(google_key.strip()) < 10:
        errors.append("INVALID: GOOGLE_API_KEY is too short or invalid.")
        
    # 2. Check for optional LangSmith keys and log warnings
    langsmith_tracing = os.getenv("LANGCHAIN_TRACING_V2")
    langsmith_key = os.getenv("LANGSMITH_API_KEY")
    if langsmith_tracing == "true" and not langsmith_key:
        logger.warning("LANGCHAIN_TRACING_V2 is set to 'true', but LANGSMITH_API_KEY is missing. Tracing will fail.")
        
    # 3. Verify Redis connection if URL is provided
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.warning("REDIS_URL is not set. Cache & Rate Limiting will be bypassed (failed open).")
    else:
        try:
            import redis
            # Check if redis server is reachable with a 2-second connection timeout
            r = redis.Redis.from_url(redis_url, socket_connect_timeout=2.0)
            r.ping()
            logger.info("Connection to Redis succeeded.")
        except ImportError:
            logger.warning("The 'redis' library is not installed. Cache & Rate Limiting will be bypassed.")
        except Exception as e:
            logger.warning(f"Connection to Redis failed: {e}. Cache & Rate Limiting will be bypassed (failed open).")
            
    # 4. Check onboarding data folder
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    if not os.path.exists(data_dir):
        logger.info(f"Creating missing data directory at: {data_dir}")
        os.makedirs(data_dir, exist_ok=True)
        
    if errors:
        logger.error("Startup Configuration Validation Failed:")
        for err in errors:
            logger.error(f"  - {err}")
        return False
        
    logger.info("Startup Configuration Validation Passed.")
    return True

if __name__ == "__main__":
    if not check_configuration():
        logger.error("Shutting down due to configuration errors.")
        sys.exit(1)
    else:
        sys.exit(0)
