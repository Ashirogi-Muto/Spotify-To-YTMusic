import time
import random
import functools
import logging
from typing import Callable, Any

from src.config import YTM_MAX_RETRIES, YTM_RATE_LIMIT_DELAY, YTM_JITTER_MAX

logger = logging.getLogger(__name__)

class RateLimitExceededException(Exception):
    pass

def yt_rate_limited(func: Callable) -> Callable:
    """
    Decorator for ytmusicapi calls to enforce:
    - 2 requests per second globally
    - 0-300ms random jitter
    - Exponential backoff (1s -> 2s -> 4s) on failure (up to 3 retries)
    """
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        retries = 0
        backoff = 1.0  # seconds

        while retries <= YTM_MAX_RETRIES:
            # 1. Enforce rate limit (delay since last call)
            current_time = time.time()
            time_since_last_call = current_time - yt_rate_limited.last_call_time
            
            if time_since_last_call < YTM_RATE_LIMIT_DELAY:
                sleep_time = YTM_RATE_LIMIT_DELAY - time_since_last_call
                time.sleep(sleep_time)
            
            # 2. Add random Jitter
            jitter = random.uniform(0, YTM_JITTER_MAX)
            time.sleep(jitter)
            
            yt_rate_limited.last_call_time = time.time()

            # 3. Execute
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"YT API Call Failed ({func.__name__}): {e}")
                if retries == YTM_MAX_RETRIES:
                    logger.error(f"Max retries reached for {func.__name__}")
                    raise e
                
                logger.info(f"Retrying in {backoff} seconds...")
                time.sleep(backoff)
                retries += 1
                backoff *= 2  # Exponential backoff (1, 2, 4...)

    return wrapper

# Initialize the state on the function object itself
yt_rate_limited.last_call_time = 0.0
