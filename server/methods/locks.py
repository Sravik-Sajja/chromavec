import os
import redis
from dotenv import load_dotenv

load_dotenv()


class _LazyRedis:
    """Defers Redis client creation until first real call."""
    def __init__(self):
        self._client = None

    def _ensure(self):
        if self._client is None:
            self._client = redis.Redis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379/0")
            )
        return self._client

    def lock(self, *args, **kwargs):
        return self._ensure().lock(*args, **kwargs)


redis_client = _LazyRedis()


def reset_redis_client():
    global redis_client
    redis_client = _LazyRedis()