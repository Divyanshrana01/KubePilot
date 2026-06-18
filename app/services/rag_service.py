from __future__ import annotations

from loguru import logger

from app.models import (
    ChatResponse,
    ResponseMetadata,
    RetrievedChunk,
    RetrievedChunkPreview,
)
from app.security.output_validator import validate_with_retry
from app.security.spotlighting import build_spotlighted_context
from app.security.system_prompt import build_system_prompt
from app.services.embedding_service import embed_texts
from app.services.llm_service import generate
from app.services.vector_store import search, hybrid_search, sparse_search
from app.services.query_cache_service import query_cache


def _flag(flags: dict | None, key: str, default):
    if not isinstance(flags, dict):
        return default
    return flags.get(key, default)


def _retrieve(question: str, flags: dict | None = None) -> list[RetrievedChunk]:
    top_k = int(_flag(flags, "top_k", 5))
    mode = _flag(flags, "search_mode", "dense")

    if mode == "sparse":
        return sparse_search(question, top_k=top_k)
    elif mode == "hybrid":
        query_embedding = embed_texts([question])[0]
        return hybrid_search(query_embedding, question, top_k=top_k)
    else:
        query_embedding = embed_texts([question])[0]
        return search(query_embedding, top_k=top_k)


def _generate(question: str, chunks: list[RetrievedChunk]) -> ChatResponse:
    spotlighted = build_spotlighted_context(chunks)
    system = build_system_prompt()
    user_message = f"{spotlighted}\n\nQuestion: {question}"
    raw = generate(system, user_message)["text"]

    #the system prompt asks the llm for a json object — parse it (retrying on bad json)
    #instead of of dumping the raw json/markdown straight into the answer field
    def _retry_llm(retry_prompt: str, _error: str) -> str:
        return generate(system, retry_prompt)["text"]

    parsed = validate_with_retry(raw, _retry_llm)

    chunk_previews = [
        RetrievedChunkPreview(text=c.text, source=c.source, score=c.score) for c in chunks
    ]
    return ChatResponse(
        answer=parsed.answer,
        sources=list({c.source for c in chunks}),
        confidence=parsed.confidence,
        metadata=ResponseMetadata(route="rag", retrieved_chunks=chunk_previews),
    )


def _cache_context(flags: dict | None) -> dict:
    return {
        "search_mode": _flag(flags, "search_mode", "dense"),
        "top_k": int(_flag(flags, "top_k", 5)),
    }


def run_rag(question: str, flags: dict | None = None) -> ChatResponse:
    cache_ctx = _cache_context(flags)
    cached = query_cache.get_rag_answer(question, cache_ctx)
    if cached is not None:
        resp = ChatResponse(**cached)
        resp.cache_hit = True
        resp.metadata.cache_hit = True
        return resp

    logger.info(
        "RAG query | mode={} top_k={}",
        _flag(flags, "search_mode", "dense"),
        int(_flag(flags, "top_k", 5)),
    )

    chunks = _retrieve(question, flags=flags)
    response = _generate(question, chunks)

    query_cache.set_rag_answer(question, response.model_dump(), cache_ctx)
    return response


#same as run_rag but bypasses the cache entirely and also returns the retrieved chunks —
#used by the eval harness, which needs fresh (uncached) runs plus the raw contexts for ragas scoring
def run_rag_with_trace_no_cache(
    question: str, flags: dict | None = None
) -> tuple[ChatResponse, list[RetrievedChunk]]:
    chunks = _retrieve(question, flags=flags)
    response = _generate(question, chunks)
    return response, chunks
