from __future__ import annotations

from app.models import ChatResponse, RetrievedChunk


def run_rag_with_trace_no_cache(
    question: str, flags: dict
) -> tuple[ChatResponse, list[RetrievedChunk]]:
    raise NotImplementedError("RAG service not yet implemented")
