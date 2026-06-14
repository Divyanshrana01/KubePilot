from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from app.config import settings
from app.models import ChatResponse, RetrievedChunk
from app.services.llm_service import run_rag_with_trace_no_cache


#raised when a golden question's intent is not supported by the current invoker.
#the eval harness catches this and marks the question as skipped instead of failed.
class SkippedIntent(Exception):
    pass

#base class for all invokers — defines the interface the eval harness uses
class Invoker(ABC):

    @abstractmethod
    def invoke(
        self, question: str, flags: dict, intent: str
    ) -> tuple[ChatResponse, list[RetrievedChunk]]:
        ...


#this invoker calls our actual RAG service directly (no http round trip).
#it only supports rag and web_fallback intents — sql and hybrid are not wired up yet.
class ServiceInvoker(Invoker):
    SUPPORTED_INTENTS = {"rag", "web_fallback"}

    def invoke(
        self, question: str, flags: dict, intent: str
    ) -> tuple[ChatResponse, list[RetrievedChunk]]:
        if intent not in self.SUPPORTED_INTENTS:
            raise SkippedIntent(f"intent={intent} not supported in service mode")

        #skip web_fallback questions if the tavily key isnt configured
        if intent == "web_fallback" and not settings.tavily_api_key:
            raise SkippedIntent("tavily_unset: TAVILY_API_KEY not configured")

        #run the full rag pipeline with the given flags, bypassing the cache
        return run_rag_with_trace_no_cache(question, flags)
