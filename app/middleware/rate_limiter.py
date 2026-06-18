import logging
import time
from upstash_redis import Redis
from app.config import settings

logger = logging.getLogger(__name__)

#shared redis client — only created once and reused across all requests
_redis_client: Redis | None = None

def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis(
            url=settings.upstash_redis_url,
            token=settings.upstash_redis_token,
        )
    return _redis_client


#this class implements a sliding window rate limiter using a redis sorted set.
#each request is stored with its timestamp as the score, so old ones can be expired out.
class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def is_allowed(self, key: str) -> tuple[bool, int, int]:
        now = time.time()
        window_start = now - self.window_seconds

        #fail open if redis is unreachable/misconfigured — a broken rate limiter
        #should never take down the endpoints it's meant to protect
        try:
            client = get_redis_client()
            #use a pipeline to run all 4 redis commands in one round trip
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)   #remove old requests outside the window
            pipe.zadd(key, {str(now): now})               #add this new request
            pipe.zcard(key)                                #count how many requests are in the window
            pipe.expire(key, self.window_seconds)          #auto-delete the key after the window expires
            results = pipe.exec()
        except Exception:
            logger.warning("Rate limiter backend unavailable, failing open for key=%s", key, exc_info=True)
            return True, self.max_requests, 0

        request_count: int = results[2]  # type: ignore[assignment]
        remaining = max(0, self.max_requests - request_count)
        allowed = request_count <= self.max_requests

        return allowed, remaining, request_count


#check rate limit by ip address + route — used on auth endpoints to block repeated attempts
def is_allowed_ip(ip: str, route: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
    limiter = RateLimiter(max_requests=limit, window_seconds=window_seconds)
    key = f"rate_limit:ip:{ip}:{route}"
    return limiter.is_allowed(key)


#check rate limit by user id — used on api endpoints after the user is logged in
def is_allowed_user(user_id: str, limit: int = 20, window_seconds: int = 60) -> tuple[bool, int, int]:
    limiter = RateLimiter(max_requests=limit, window_seconds=window_seconds)
    key = f"rate_limit:user:{user_id}"
    return limiter.is_allowed(key)
