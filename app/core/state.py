from operator import add
from typing import Annotated, TypedDict

from app.models import CRAGEvaluation, ReflectionResult, RetrievedChunk

class GraphState(TypedDict):
    """Shared state threaded through every node of the LangGraph workflow (see app/core/graph.py).

    Each node returns a partial dict of these keys; LangGraph merges that
    dict into the running state. Fields are grouped below by the phase of
    the pipeline that populates them. Most fields are simply overwritten on
    each update — `retrieved_chunks` is the exception, since it's marked
    with the `add` reducer so repeated writes (e.g. multiple Self-RAG
    reflection passes) append rather than replace.
    """

    # --- Input, set once at the start of a run ---
    question: str
    user_id: str
    flags: dict

    # --- Routing: which path (sql / rag / hybrid) classify_intent picked ---
    intent: str | None

    # --- SQL path: populated by generate_sql_node / request_sql_approval / execute_sql ---
    generated_sql: str | None
    sql_explanation: str | None
    sql_approved: bool | None
    sql_rows: list[dict] | None
    sql_cache_hit: bool


    # --- RAG path: populated by run_rag / retrieve_rag and the Self-RAG/CRAG pipeline ---
    hypotheses: list[str]
    # Annotated with `add` so each node's contribution is appended to the
    # existing list instead of overwriting it across reflection iterations.
    retrieved_chunks: Annotated[list[RetrievedChunk], add]
    reranked_chunks: list[RetrievedChunk] | None
    spotlighted_context: str | None
    crag_evaluation: CRAGEvaluation | None
    web_results: list[RetrievedChunk]
    rag_cache_hit: bool

    # --- Self-RAG reflection: tracks how many times the answer was critiqued/refined ---
    raw_answer: str | None
    reflection: ReflectionResult | None
    reflection_iterations: int
    refined_question: str | None

    # --- Output: consumed by generate_answer/finalize and returned to the API caller ---
    final_answer: str | None
    sources: list[str]
    confidence: float | None
    chunk_previews: list[dict]

    # --- Telemetry: cache hits and cost savings surfaced for observability ---
    cache_hits: dict[str, bool]
    cost_saved_usd: float