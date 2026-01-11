"""Redis client factory with connection retry logic.

Standalone module without relative imports for use in Docker services.
"""

import sys
import time
import random

import redis
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError


class RedisStartupError(Exception):
    """Failed to connect to Redis after all retries."""
    pass


def create_redis_client(
    redis_url: str,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0
) -> redis.Redis:
    """Create Redis client with exponential backoff retry.

    Args:
        redis_url: Redis connection URL
        max_retries: Maximum connection attempts (default 5)
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay cap in seconds

    Returns:
        Connected Redis client

    Raises:
        RedisStartupError: If connection fails after all retries
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            return client
        except (RedisConnectionError, RedisTimeoutError, OSError) as e:
            last_error = e
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = delay * 0.25 * (2 * random.random() - 1)
            actual_delay = delay + jitter

            print(
                f"Redis connection failed (attempt {attempt + 1}/{max_retries}): {e}",
                file=sys.stderr
            )

            if attempt < max_retries - 1:
                print(f"Retrying in {actual_delay:.1f}s...", file=sys.stderr)
                time.sleep(actual_delay)

    raise RedisStartupError(
        f"Failed to connect to Redis at {redis_url} after {max_retries} attempts: {last_error}"
    )
