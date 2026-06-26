# Admin-only endpoints: system health checks and cache stats/management.
import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from loguru import logger

from app.config import settings


from app.middleware.auth import User, get_current_admin_user
from app.services.query_cache_service import query_cache




router = APIRouter(tags=["admin"])

#each _ping_* probe lazily imports its client and returns a plain bool, swallowing every
#error into False. one dependency being down should report as "degraded", never raise -
#the health endpoint has to stay answerable even when half the stack is unreachable.
async def _ping_postgres() -> bool:
    """Check whether the Postgres database is reachable."""
    try:
        import psycopg2

        conn = psycopg2.connect(settings.database_url, connect_timeout=2)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return True
    except Exception as exc:
        logger.debug("Postgres health check failed: {}", exc)
        return False

async def _ping_qdrant() -> bool:
    """Check whether the Qdrant vector database is reachable."""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=settings.qdrant_url, timeout=2)
        client.get_collections()
        return True
    except Exception as exc:
        logger.debug("Qdrant health check failed: {}", exc)
        return False

async def _ping_redis() -> bool:
    """Check whether the Redis cache is reachable."""
    try:
        from upstash_redis import Redis

        redis = Redis(url=settings.upstash_redis_url, token=settings.upstash_redis_token)
        redis.ping()
        return True
    except Exception as exc:
        logger.debug("Redis health check failed: {}", exc)
        return False

async def _ping_openai() -> bool:
    """Check whether the OpenAI API is reachable with the configured key."""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        await client.models.list()
        return True
    except Exception as exc:
        logger.debug("OpenAI health check failed: {}", exc)
        return False

async def _ping_tavily() -> bool:
    """Check whether the Tavily web search service is reachable."""
    try:
        from app.services.web_search import search_web

        search_web("health check")
        return True
    except ValueError:
        # Tavily key not configured — still "up" if the module loads
        return True
    except Exception as exc:
        logger.debug("Tavily health check failed: {}", exc)
        return False





#unauthenticated on purpose: this is the liveness/readiness probe (docker, load balancer, etc),
#so it can't sit behind admin auth. it only ever leaks up/down booleans, never any secrets.
@router.get("/admin/health")
async def health_check() -> dict[str, Any]:
    """Ping all external dependencies in parallel and report overall system status."""
    #gather with return_exceptions=True so one probe blowing up doesn't cancel the rest;
    #any slot that came back as an Exception is then coerced to False (treated as down)
    results = await asyncio.gather(
        _ping_postgres(),
        _ping_qdrant(),
        _ping_redis(),
        _ping_openai(),
        _ping_tavily(),
        return_exceptions=True,
    )
    postgres_ok = bool(results[0]) if not isinstance(results[0], Exception) else False
    qdrant_ok = bool(results[1]) if not isinstance(results[1], Exception) else False
    redis_ok = bool(results[2]) if not isinstance(results[2], Exception) else False
    openai_ok = bool(results[3]) if not isinstance(results[3], Exception) else False
    tavily_ok = bool(results[4]) if not isinstance(results[4], Exception) else False

    all_ok = postgres_ok and qdrant_ok and redis_ok and openai_ok and tavily_ok
    status = "ok" if all_ok else "degraded"

    return {
        "status": status,
        "qdrant": qdrant_ok,
        "postgres": postgres_ok,
        "redis": redis_ok,
        "openai": openai_ok,
        "tavily": tavily_ok
    }


#admin-gated (unlike /admin/health) since cache internals are operational detail, not a liveness probe
@router.get("/admin/cache/stats")
async def cache_stats(user: User = Depends(get_current_admin_user)) -> dict:
    """Return per-cache hit/miss/set counts."""
    #raw keys are the internal tier names from query_cache._TIERS; we remap to friendlier
    #response keys (e.g. rag_answer -> "rag") and default any missing tier to zeros
    raw = query_cache.stats()

    def _tier(name: str) -> dict:
        """Pull out the stats for one named cache tier, defaulting missing values to 0."""
        return {
            "hits": int(raw.get(name, {}).get("hits", 0)),
            "misses": int(raw.get(name, {}).get("misses", 0)),
            "sets": int(raw.get(name, {}).get("sets", 0)),
            "hit_rate": float(raw.get(name, {}).get("hit_rate", 0.0)),
        }

    return {
        "embedding": _tier("embedding"),
        "rag": _tier("rag_answer"),
        "sql_gen": _tier("sql_gen"),
        "sql_result": _tier("sql_result"),
        "intent_router": _tier("intent"),
    }



@router.post("/admin/cache/clear")
async def cache_clear(user: User = Depends(get_current_admin_user)) -> dict:
    """Clear all caches (Redis + in-memory)."""
    cleared = query_cache.clear()
    return {"status": "ok", "cleared": cleared}