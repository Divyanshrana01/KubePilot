# Builds and wires up the LangGraph state machine that powers RAG/SQL/hybrid question answering.
import datetime
import decimal
import json
import uuid
from typing import Any

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.config import settings
from app.core.state import GraphState
from app.security.spotlighting import build_spotlighted_context
from app.security.system_prompt import build_chitchat_system_prompt
from app.services.llm_service import generate
from app.services.rag_service import run_rag
from app.services.router_service import classify_intent
from app.services.sql_service import SQLService


sql_service = SQLService()


def _safe_json_default(obj: Any) -> Any:
    """Fallback serializer for non-JSON-native types.

    SQL rows coming back from psycopg can contain driver-native types
    (Decimal, UUID, dates, bytes) that json.dumps doesn't know how to
    handle, so each one is converted to a JSON-friendly representation here.
    """
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, datetime.time):
        return obj.isoformat()
    if isinstance(obj, datetime.timedelta):
        return str(obj)
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _safe_json_dumps(obj: Any, **kwargs: Any) -> str:
    """json.dumps with a safe fallback for exotic types."""
    return json.dumps(obj, default=_safe_json_default, **kwargs)


def route_intent(state: GraphState) -> dict:
    """LLM-based intent router for sql/rag/hybrid.

    This is the entry node (see build_graph) — its output decides which
    branch the rest of the graph takes via the conditional edge keyed
    on `state["intent"]`.
    """
    intent = classify_intent(state["question"])
    return {"intent": intent}


def retrieve_rag(state: GraphState) -> dict:
    """Run document retrieval and wrap the results in a spotlighted (clearly-untrusted) context block.

    Only reached on the "hybrid" path (see build_graph), to gather document
    context before the SQL side of the answer is generated.
    """
    response = run_rag(state["question"], flags=state.get("flags", {}))
    return {
        "retrieved_chunks": response.sources,
        # build_spotlighted_context expects chunk-like objects with
        # text/source/score attributes; run_rag only gives us plain source
        # strings here, so a throwaway object is built on the fly to satisfy
        # that interface instead of changing run_rag's return shape.
        "spotlighted_context": build_spotlighted_context([
            type("Chunk", (), {"text": s, "source": s, "score": 0.0})()
            for s in response.sources
        ]),
        # "rag_cache_hit": response.cache_hit,
        # "cache_hits": {"rag_answer": response.cache_hit},
    }


def generate_sql_node(state: GraphState) -> dict:
    """Ask the SQL service to turn the question into a SQL query plus an explanation."""
    result = sql_service.generate_sql(state["question"])
    return {
        "generated_sql": result["sql"],
        "sql_explanation": result["explanation"],
    }



def request_sql_approval(state: GraphState) -> dict:
    """Pause the graph and wait for a human to approve/reject the generated SQL before running it.

    `interrupt()` suspends execution here and persists state via the
    Postgres checkpointer (see _get_checkpointer); the graph resumes once
    an external caller supplies {"approved": bool} to continue the run.
    """
    approval = interrupt({
        "type": "sql_approval_required",
        "sql": state["generated_sql"],
        "explanation": state["sql_explanation"],
    })
    return {"sql_approved": approval.get("approved", False)}

def execute_sql(state: GraphState) -> dict:
    """Execute approved SQL and store results."""
    if not state.get("sql_approved"):
        # Approval was rejected (or never granted) — skip execution and let
        # generate_answer pass this message straight through as the answer.
        return {"sql_rows": [], "final_answer": "SQL query was not approved."}

    sql = state.get("generated_sql", "")
    try:
        rows = sql_service.execute_sql(sql)
        return {"sql_rows": rows}
    except Exception as exc:
        # Don't let a bad SQL query crash the whole graph; surface the error as the answer instead.
        return {"sql_rows": [], "final_answer": f"SQL execution failed: {exc}"}



def _synthesize_sql_answer(question: str, rows: list) -> str:
    """Turn raw SQL result rows into a natural-language answer via the LLM.

    Without this the user just sees a JSON dump of the rows. We hand the model the
    original question plus the result rows and ask it to phrase a direct answer,
    grounded only on those rows (so it can't invent numbers that aren't there).
    """
    results_json = _safe_json_dumps(rows, indent=2)
    system = (
        "You are a Kubernetes IT-Operations / SRE assistant. You are given a user's question "
        "and the rows returned by a SQL query that was run to answer it. Write a concise, "
        "direct, natural-language answer to the question based ONLY on these rows. State the "
        "key figure(s) plainly in a full sentence. If the rows are empty, say no matching "
        "records were found. Do not invent data that isn't in the rows. Cite the source as "
        "[database query]."
    )
    user_msg = f"Question: {question}\n\nSQL result rows (JSON):\n{results_json}"
    return generate(system, user_msg)["text"]


def generate_answer(state: GraphState) -> dict:
    """Produce the final answer, branching by intent: chit-chat, SQL results, hybrid synthesis, or plain RAG."""
    intent = state.get("intent", "rag")

    if intent == "chitchat":
        # Greetings / small talk: reply directly, no retrieval, no sources.
        reply = generate(build_chitchat_system_prompt(), state["question"])["text"]
        return {
            "final_answer": reply,
            "sources": [],
            "confidence": 1.0,
            "metadata": {"route": "chitchat"},
        }

    if intent == "sql":
        rows = state.get("sql_rows", [])
        # surface the SQL that was generated/run so the UI can show it in a disclosure
        sql_meta = {"route": "sql", "executed_sql": state.get("generated_sql", "")}
        # execute_sql sets final_answer only when the query failed or was rejected —
        # surface that message directly rather than running it through the LLM.
        preset = state.get("final_answer")
        if preset:
            return {
                "final_answer": preset,
                "sources": ["database query"],
                "confidence": 0.9,
                "metadata": sql_meta,
            }
        # Otherwise turn the result rows (an empty set included) into a natural-language
        # answer instead of dumping raw JSON at the user.
        return {
            "final_answer": _synthesize_sql_answer(state["question"], rows),
            "sources": ["database query"],
            "confidence": 0.9,
            "metadata": sql_meta,
        }

    if intent == "hybrid":
        return _generate_hybrid_answer(state)

    response = run_rag(state["question"], flags=state.get("flags", {}))
    chunk_previews = [
        chunk.model_dump() for chunk in response.metadata.retrieved_chunks
    ]

    return {
        "final_answer": response.answer,
        "sources": response.sources,
        "confidence": response.confidence,
        "cache_hit": response.cache_hit,
        "chunk_previews": chunk_previews,
        "metadata": response.metadata.model_dump(),
        # Surface Self-RAG telemetry so the API can include it in the response.
        "reflection_iterations": response.metadata.reflection_iterations,
        "refined_question": response.metadata.refined_question,
    }


def _generate_hybrid_answer(state: GraphState) -> dict:
    """Combine SQL query results and retrieved documents into one LLM-written answer."""
    rows = state.get("sql_rows", [])
    rag_context = state.get("spotlighted_context", "")

    sql_section = ""
    if rows:
        sql_section = f"=== Database Query Results ===\n```\n{_safe_json_dumps(rows, indent=2)}\n```\n"

    rag_section = f"=== Retrieved Documents ===\n{rag_context}\n" if rag_context else ""

    system = (
        "You are an AI assistant. Synthesize database query results and "
        "retrieved documents into a single coherent answer. Cite sources using "
        "[database query] for SQL results and [source_name] for documents."
    )
    user_msg = f"{sql_section}{rag_section}\n\nQuestion: {state['question']}"

    result = generate(system, user_msg)
    return {
        "final_answer": result["text"],
        "sources": ["database query"] + state.get("retrieved_chunks", []),
        "confidence": 0.85,
    }

def finalize(state: GraphState) -> dict:
    """No-op end node; exists so the graph has a single terminal step before END."""
    return {}

def _get_checkpointer():
    """Set up Postgres-backed checkpointing so graph runs can be paused/resumed (e.g. for SQL approval).

    autocommit=True is required by PostgresSaver, which manages its own
    transactions internally rather than relying on the caller to commit.
    `saver.setup()` creates the checkpoint tables on first run (no-op after).
    """
    conn = psycopg.connect(settings.database_url, autocommit=True)
    saver = PostgresSaver(conn=conn)
    saver.setup()
    return saver




def build_graph():
    """Wire up all the nodes and edges that define the question-answering workflow."""
    builder = StateGraph(GraphState)
    builder.add_node("route_intent", route_intent)
    builder.add_node("retrieve_rag", retrieve_rag)
    builder.add_node("generate_sql_node", generate_sql_node)
    builder.add_node("request_sql_approval", request_sql_approval)
    builder.add_node("execute_sql", execute_sql)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "route_intent")
    # Branch to a different path depending on whether the question needs SQL, RAG, or both:
    #   sql    -> generate SQL directly
    #   rag    -> skip SQL entirely, answer straight from retrieval
    #   hybrid -> retrieve documents first, then also generate SQL, then merge both
    builder.add_conditional_edges(
        "route_intent",
        lambda s: s.get("intent", "rag"),
        {
            "sql": "generate_sql_node",
            "rag": "generate_answer",
            "hybrid": "retrieve_rag",
            "chitchat": "generate_answer",
        },
    )
    # hybrid path: retrieved docs feed into the same SQL generation/approval/execution
    # pipeline used by the sql path, so both branches converge here.
    builder.add_edge("retrieve_rag", "generate_sql_node")
    builder.add_edge("generate_sql_node", "request_sql_approval")
    builder.add_edge("request_sql_approval", "execute_sql")
    builder.add_edge("execute_sql", "generate_answer")
    builder.add_edge("generate_answer", "finalize")
    builder.add_edge("finalize", END)

    checkpointer = _get_checkpointer()
    return builder.compile(checkpointer=checkpointer)

# Build the graph once at import time so all requests share the same compiled graph.
graph = build_graph()
