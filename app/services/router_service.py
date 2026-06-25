import json
import logging
from typing import Literal

from app.config import settings
from app.services.llm_service import generate_with_json
from app.services.query_cache_service import query_cache

Intent = Literal["sql", "rag", "hybrid"]

_INTENT_SYSTEM_PROMPT = """You are an intent classifier for a Kubernetes IT-Operations and SRE AI assistant.
Classify the user question into exactly one of these categories:
- "sql": Questions about numerical data, counts, totals, sums, averages, or specific operational facts stored in a database (e.g., "how many P1 incidents last quarter", "average MTTR for network incidents", "which cluster has the most CrashLoopBackOff pods", "pods in the production namespace")
- "rag": Questions about concepts, procedures, troubleshooting steps, or general Kubernetes knowledge found in documentation or runbooks (e.g., "how to scale a deployment", "what is a StatefulSet", "kubectl rollback procedure", "P1 incident escalation process")
- "hybrid": Questions that require both operational data from the database AND conceptual knowledge from documentation (e.g., "how many image pull failure incidents occurred last month and what are the remediation steps")

If the question does not relate to Kubernetes operations, incidents, or documentation at all, classify it as "rag".

Respond ONLY with a JSON object in this exact format:
{"intent": "sql"} or {"intent": "rag"} or {"intent": "hybrid"}
"""

logger = logging.getLogger(__name__)


# Kubernetes resource/concept terms that only appear in the docs corpus, never in the
# incident database. If a question contains one, route straight to "rag" without
# spending an LLM call on classification.
_DOCUMENT_HINTS = (
    "statefulset",
    "daemonset",
    "deployment",
    "configmap",
    "rbac",
    "ingress",
    "namespace",
    "persistent volume",
    "service account",
    "liveness probe",
    "readiness probe",
    "resource quota",
    "scheduler",
    "kubectl",
    "node-pressure",
    "eviction",
    "pod priority",
    "network policy",
    "storage class",
)

def _looks_like_document_question(question: str) -> bool:
    lowered = question.lower()
    return any(hint in lowered for hint in _DOCUMENT_HINTS)


def classify_intent(question: str) -> Intent:
    # Checked before the cache lookup since this match is free and always correct,
    # so there's no need to pay a cache round-trip for these questions either.
    if _looks_like_document_question(question):
        query_cache.set_intent(question, "rag")
        return "rag"

    cached = query_cache.get_intent(question)
    if cached in ("sql", "rag", "hybrid"):
        return cached

    try:
        response = generate_with_json(
            system_prompt=_INTENT_SYSTEM_PROMPT,
            user_message=question,
            model=settings.llm_model_grader,
            temperature=0.0,
        )
        raw_text = response.get("text", "")
        parsed = json.loads(raw_text)
        intent = parsed.get("intent", "")

        if intent in ("sql", "rag", "hybrid"):
            query_cache.set_intent(question, intent)
            return intent  # type: ignore[return-value]

        # The model didn't return one of the three allowed values (e.g. hallucinated
        # a different label). Treat that as unclassifiable and route to "rag" rather
        # than letting an unexpected value reach the caller.
        logger.error("Invalid intent returned by LLM: %s", intent)
        return "rag"
    except Exception:
        # Covers request failures, malformed JSON, etc. The router must always return
        # an Intent, so any error here falls back to "rag" instead of propagating.
        logger.exception("Intent classification failed, falling back to rag")
        return "rag"