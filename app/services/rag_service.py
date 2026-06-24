from __future__ import annotations

from loguru import logger

from app.models import (
    ChatResponse,
    CRAGEvaluation,
    ResponseMetadata,
    RetrievedChunk,
    RetrievedChunkPreview,
)
from app.config import settings
from app.security.output_validator import validate_with_retry
from app.security.spotlighting import build_spotlighted_context
from app.security.system_prompt import build_system_prompt
from app.services.embedding_service import embed_texts
from app.services.llm_service import generate
from app.services.reranking import Reranker
from app.services.vector_store import search, hybrid_search, sparse_search
from app.services.query_cache_service import query_cache
from app.services.hyde import HyDERetriever
from app.services.crag import crag_pipeline
from app.services.self_reflective import reflect_on_answer, should_regenerate


_reranker = Reranker()
_hyde_retriever = HyDERetriever()


#small helper so we dont have to null check flags everywhere, just returns the default if missing
def _flag(flags: dict | None, key: str, default):
    if not isinstance(flags, dict):
        return default
    return flags.get(key, default)


#picks which search fn to use based on the search_mode flag and runs it.
#if reranking is on, we overfetch a larger candidate pool first since the reranker
#needs more options than top_k to actually improve on the initial ranking.
def _retrieve(question: str, flags: dict | None = None) -> list[RetrievedChunk]:
    top_k = int(_flag(flags, "top_k", 5))
    mode = _flag(flags, "search_mode", "dense")
    use_rerank = bool(_flag(flags, "rerank", settings.reranking_enabled_by_default))
    use_hyde = bool(_flag(flags, "hyde", settings.hyde_enabled_by_default))
    fetch_k = max(top_k, settings.reranker_initial_top_k) if use_rerank else top_k

    if mode == "sparse":
        candidates = sparse_search(question, top_k=fetch_k)
    elif mode == "hybrid":
        query_embedding = embed_texts([question])[0]
        candidates = hybrid_search(query_embedding, question, top_k=fetch_k)
    elif use_hyde:
        #hyde only makes sense for dense search since it works by generating extra
        #texts to embed and search with, not by changing how sparse/hybrid scoring works
        candidates = _hyde_retriever.retrieve(question, top_k=fetch_k)
    else:
        query_embedding = embed_texts([question])[0]
        candidates = search(query_embedding, top_k=fetch_k)

    if use_rerank:
        return _reranker.rerank(question, candidates, top_k=top_k)
    return candidates


#wraps the chunks with the spotlight warning, calls the llm, then parses its json reply
def _generate(
    question: str,
    chunks: list[RetrievedChunk],
    crag_evaluation: CRAGEvaluation | None = None,
    crag_triggered: bool = False,
    flags: dict | None = None,
) -> ChatResponse:
    enable_self_reflective = bool(_flag(flags, "enable_self_reflective", False))

    spotlighted = build_spotlighted_context(chunks)
    system = build_system_prompt()

    #the system prompt asks the llm for a json object, so we parse it here instead of
    #just dumping the raw json/markdown straight into the answer field. retries on bad json
    def _retry_llm(retry_prompt: str, _error: str) -> str:
        return generate(system, retry_prompt)["text"]

    def _ask(q: str):
        raw = generate(system, f"{spotlighted}\n\nQuestion: {q}")["text"]
        return validate_with_retry(raw, _retry_llm)

    working_q = question
    parsed = _ask(working_q)

    # Self-RAG: reflect on the answer; refine the question and retry if weak.
    iterations = 0
    last_score: float | None = None
    final_refined: str | None = None
    if enable_self_reflective:
        while True:
            reflection = reflect_on_answer(
                question=working_q,
                answer=parsed.answer,
                context=spotlighted,
            )
            last_score = float(reflection.reflection_score)
            if not should_regenerate(reflection, iterations):
                break
            final_refined = reflection.refined_question or working_q
            working_q = final_refined
            parsed = _ask(working_q)
            iterations += 1

    chunk_previews = [
        RetrievedChunkPreview(text=c.text, source=c.source, score=c.score) for c in chunks
    ]
    return ChatResponse(
        answer=parsed.answer,
        sources=list({c.source for c in chunks}),
        confidence=parsed.confidence,
        metadata=ResponseMetadata(
            route="rag",
            retrieved_chunks=chunk_previews,
            crag_triggered=crag_triggered,
            crag_relevance_score=crag_evaluation.relevance_score if crag_evaluation else None,
            reflection_iterations=iterations,
            reflection_score=last_score,
            refined_question=final_refined,
        ),
    )



#these flags get baked into the cache key, so different settings dont share the same cached answer
def _cache_context(flags: dict | None) -> dict:
    use_rerank = bool(_flag(flags, "rerank", settings.reranking_enabled_by_default))
    return {
        "search_mode": _flag(flags, "search_mode", "dense"),
        "top_k": int(_flag(flags, "top_k", 5)),
        "rerank": use_rerank,
        "rerank_backend": settings.reranker_backend if use_rerank else None,
        "hyde": bool(_flag(flags, "hyde", settings.hyde_enabled_by_default)),
        "crag": bool(_flag(flags, "enable_crag", settings.crag_enabled_by_default)),
        "self_reflective": bool(_flag(flags, "enable_self_reflective", False)),
    }


#grades the retrieved chunks and swaps in web search results if theyre not relevant enough
def _apply_crag(
    question: str, chunks: list[RetrievedChunk], flags: dict | None
) -> tuple[list[RetrievedChunk], CRAGEvaluation, bool]:
    enable_crag = bool(_flag(flags, "enable_crag", settings.crag_enabled_by_default))
    return crag_pipeline(question, chunks, enable_crag=enable_crag)


#main entry point: checks cache first, otherwise retrieves chunks and generates an answer
def run_rag(question: str, flags: dict | None = None) -> ChatResponse:
    cache_ctx = _cache_context(flags)
    cached = query_cache.get_rag_answer(question, cache_ctx)
    if cached is not None:
        resp = ChatResponse(**cached)
        resp.cache_hit = True
        resp.metadata.cache_hit = True
        return resp

    logger.info(
        "RAG query | mode={} top_k={} rerank={} hyde={} crag={}",
        cache_ctx["search_mode"],
        cache_ctx["top_k"],
        cache_ctx["rerank"],
        cache_ctx["hyde"],
        cache_ctx["crag"],
    )

    chunks = _retrieve(question, flags=flags)
    chunks, evaluation, triggered = _apply_crag(question, chunks, flags)
    if triggered:
        logger.info(
            "CRAG fell back to web search | relevance={} label={}",
            evaluation.relevance_score,
            evaluation.relevance_label,
        )
    response = _generate(
        question, chunks, crag_evaluation=evaluation, crag_triggered=triggered, flags=flags
    )

    query_cache.set_rag_answer(question, response.model_dump(), cache_ctx)
    return response


#same as run_rag but skips the cache entirely and also returns the retrieved chunks.
#the eval harness uses this since it needs fresh, uncached runs plus the raw contexts for ragas
def run_rag_with_trace_no_cache(
    question: str, flags: dict | None = None
) -> tuple[ChatResponse, list[RetrievedChunk]]:
    chunks = _retrieve(question, flags=flags)
    chunks, evaluation, triggered = _apply_crag(question, chunks, flags)
    response = _generate(
        question, chunks, crag_evaluation=evaluation, crag_triggered=triggered, flags=flags
    )
    return response, chunks
