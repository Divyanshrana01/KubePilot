"""Per-user daily token budget tracked in Redis."""

import datetime
import logging

from upstash_redis import Redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis(
            url=settings.upstash_redis_url,
            token=settings.upstash_redis_token,
        )
    return _redis_client


#tracks how many tokens a user has burned today and stops them once they hit the daily cap
class TokenBudget:
    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens

    #one redis key per user per day, so it resets automatically when the date changes
    def _key(self, user_id: str) -> str:
        today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
        return f"token_budget:{user_id}:{today}"

    #call this before the llm call to see if the user has enough tokens left.
    #fails open (same as the rate limiter) so a redis hiccup never blocks a request -
    #a broken budget check shouldn't take down the endpoint its supposed to protect
    def check_budget(self, user_id: str, estimated_tokens: int) -> tuple[bool, int]:
        try:
            client = get_redis_client()
            key = self._key(user_id)
            used_str = client.get(key)
            used = int(used_str) if used_str is not None else 0
            remaining = self.max_tokens - used
            ok = estimated_tokens <= remaining
            return ok, remaining
        except Exception:
            logger.warning("Token budget backend unavailable, failing open for user=%s", user_id, exc_info=True)
            return True, self.max_tokens

    #call this after the llm call with the real token count to update the running total.
    #also fails open - if this throws after an answer was already generated, the user
    #should still get their answer instead of a 500 over an accounting side-effect
    def consume(self, user_id: str, actual_tokens: int) -> dict:
        try:
            client = get_redis_client()
            key = self._key(user_id)
            used = client.incrby(key, actual_tokens)

            # set ttl so the key expires at midnight, only need to do this once per day
            ttl = client.ttl(key)
            if ttl == -1:
                now = datetime.datetime.now(datetime.UTC)
                midnight = (now + datetime.timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                seconds_until_midnight = int((midnight - now).total_seconds())
                client.expire(key, seconds_until_midnight)

            remaining = max(0, self.max_tokens - used)
            return {
                "used": used,
                "limit": self.max_tokens,
                "remaining": remaining,
                "tokens_charged": actual_tokens,
            }
        except Exception:
            logger.warning("Token budget backend unavailable, skipping charge for user=%s", user_id, exc_info=True)
            return {
                "used": 0,
                "limit": self.max_tokens,
                "remaining": self.max_tokens,
                "tokens_charged": 0,
            }


_budget = TokenBudget(max_tokens=settings.max_tokens_per_user_per_day)


def check_budget(user_id: str, estimated_tokens: int) -> tuple[bool, int]:
    return _budget.check_budget(user_id, estimated_tokens)


def consume_budget(user_id: str, actual_tokens: int) -> dict:
    return _budget.consume(user_id, actual_tokens)