import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from loguru import logger

from app.config import settings
from app.core.graph import graph
from app.middleware.auth import User, get_current_user
from app.middleware.rate_limiter import is_allowed_user
from app.models import ChatResponse, PendingSQLBlock, QueryRequest, SQLApprovalRequest
from app.security.content_moderation import moderate_and_redact, redact_pii
from app.security.input_guard import check_input_safe
from app.security.input_restructuring import count_tokens, restructure_input
from app.security.token_budget import check_budget, consume_budget
from app.services.rag_service import run_chitchat_stream, run_rag_stream
from app.services.router_service import classify_intent

router = APIRouter(tags=["query"])


#rough total-token estimate for the budget check: the question itself plus headroom for the reply
def _estimate_tokens(question: str) -> int:
    return count_tokens(question) + settings.reserved_output_tokens


#runs the input-side safety pipeline shared by /query and /query/stream: per-user rate limit,
#daily token budget, input restructuring, llm-guard scan, and PII redaction. Raises the right
#HTTPException on any block/limit; returns the cleaned question plus the estimated token spend
#so the caller can consume the budget once an answer is actually produced.
def _prepare_input(question: str, user: User) -> tuple[str, int]:
    allowed, _, _ = is_allowed_user(
        user.id,
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_time_window_seconds,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    estimated = _estimate_tokens(question)
    ok, remaining = check_budget(user.id, estimated)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You have {remaining} tokens remaining today; "
                f"this request estimated to use {estimated}."
            ),
        )

    restructured, _method = restructure_input(question)

    guard_allowed, guard_reason = check_input_safe(restructured)
    if not guard_allowed:
        raise HTTPException(status_code=400, detail=f"injection_blocked: {guard_reason}")

    #check_input_safe already gated toxicity/injection/banned-topics; here we only redact PII
    #from the question before it reaches retrieval / the llm (no duplicate toxicity scan).
    moderated_in = redact_pii(restructured)
    return moderated_in, estimated


#builds the per-request flag dict the rag pipeline expects. keys must stay "hyde"/"rerank"
#(not "enable_hyde"/"enable_rerank") to match _flag()/_cache_context() in rag_service.py.
def _flags_from_body(body: QueryRequest) -> dict:
    flags = {
        "top_k": body.top_k,
        "search_mode": body.search_mode,
        "hyde": body.enable_hyde,
        "enable_crag": body.enable_crag,
        "enable_self_reflective": body.enable_self_reflective,
    }
    if body.enable_rerank is not None:
        flags["rerank"] = body.enable_rerank
    return flags


#turns a graph-run's final state into the response shape the api returns.
#shared by both /query and /query/approve since they both end up reading the same state
def _response_from_state(result: dict, thread_id: str) -> ChatResponse:
    if "__interrupt__" in result:
        #graph paused to ask a human to approve a generated sql query before running it
        intr = result["__interrupt__"][0].value
        return ChatResponse(
            answer="",
            sources=[],
            confidence=0.0,
            pending_sql=PendingSQLBlock(
                sql=intr.get("sql", ""),
                query_id=thread_id,
                explanation=intr.get("explanation", ""),
            ),
        )

    return ChatResponse(
        answer=result.get("final_answer", ""),
        sources=result.get("sources", []),
        confidence=result.get("confidence", 0.0),
        cache_hit=result.get("cache_hit", False),
        metadata=result.get("metadata", {}),
    )


#main endpoint the ui calls to ask a question. runs the safety pipeline first (rate
#limit, token budget, input restructuring/guard/moderation), then the rag/sql graph,
#which itself pauses for human approval before running any generated sql
#NOTE: this is a sync `def` (not `async def`) on purpose. The whole pipeline below is
#blocking work — llm-guard CPU model scans, the sync OpenAI client, graph.invoke, Postgres
#checkpoint writes. FastAPI runs sync path operations in its threadpool, so one slow request
#no longer blocks the event loop (and every other in-flight request) the way an `async def`
#doing blocking work would.
@router.post("/query", response_model=ChatResponse)
def query(
    body: QueryRequest,
    user: User = Depends(get_current_user),
) -> ChatResponse:
    #rate limit, token budget, input restructuring, llm-guard scan, PII redaction
    moderated_in, estimated = _prepare_input(body.question, user)
    flags = _flags_from_body(body)

    thread_id = str(uuid.uuid4())
    result = graph.invoke(
        {"question": moderated_in, "user_id": user.id, "flags": flags},
        config={"configurable": {"thread_id": thread_id}},
    )

    response = _response_from_state(result, thread_id)

    #sql approval is still pending - nothing was generated yet, so there's nothing to
    #moderate or charge for. the budget/moderation steps below run once an answer exists
    if response.pending_sql is not None:
        return response

    #layer: redact pii from the answer before it goes out
    out_allowed, redacted, _ = moderate_and_redact(response.answer)
    if not out_allowed:
        raise HTTPException(status_code=500, detail="output_blocked")
    response.answer = redacted

    #only charge the budget once the request actually produced an answer
    consume_budget(user.id, estimated)

    return response


#serialize one event dict as a Server-Sent Events frame
def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


#streaming counterpart of /query. Returns text/event-stream so the UI can show pipeline
#progress (retrieving -> grading -> generating) and the answer token-by-token instead of
#staring at a spinner for the whole multi-stage pipeline. The input safety pipeline runs
#synchronously up front (so a block still returns a normal HTTP error before streaming
#starts); only the RAG answer path streams. SQL/hybrid intents need human approval, which
#can't be a single forward stream, so they're emitted as one terminal `done` event carrying
#the pending_sql block — the client then approves via the existing /query/sql/execute.
@router.post("/query/stream")
def query_stream(
    body: QueryRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    moderated_in, estimated = _prepare_input(body.question, user)
    flags = _flags_from_body(body)

    def event_gen():
        try:
            yield _sse({"type": "stage", "stage": "routing"})
            intent = classify_intent(moderated_in)

            #greetings / small talk: stream a direct reply, skip retrieval entirely
            if intent == "chitchat":
                for ev in run_chitchat_stream(moderated_in):
                    if ev.get("type") == "done":
                        _allowed, redacted, _ = moderate_and_redact(ev.get("answer", ""))
                        ev = {**ev, "answer": redacted}
                    yield _sse(ev)
                consume_budget(user.id, estimated)
                return

            if intent == "rag":
                for ev in run_rag_stream(moderated_in, flags=flags):
                    if ev.get("type") == "done":
                        #redact PII from the assembled answer before the final payload
                        _allowed, redacted, _ = moderate_and_redact(ev.get("answer", ""))
                        ev = {**ev, "answer": redacted}
                    yield _sse(ev)
                consume_budget(user.id, estimated)
                return

            #sql / hybrid: run the graph to either the approval interrupt or a final answer
            thread_id = str(uuid.uuid4())
            result = graph.invoke(
                {"question": moderated_in, "user_id": user.id, "flags": flags},
                config={"configurable": {"thread_id": thread_id}},
            )
            response = _response_from_state(result, thread_id)

            if response.pending_sql is not None:
                #nothing generated yet — hand the client the SQL to approve, don't charge budget
                yield _sse({
                    "type": "done",
                    "answer": "",
                    "sources": [],
                    "confidence": 0.0,
                    "cache_hit": False,
                    "pending_sql": response.pending_sql.model_dump(),
                    "metadata": response.metadata.model_dump(),
                })
                return

            _allowed, redacted, _ = moderate_and_redact(response.answer)
            yield _sse({
                "type": "done",
                "answer": redacted,
                "sources": response.sources,
                "confidence": response.confidence,
                "cache_hit": response.cache_hit,
                "pending_sql": None,
                "metadata": response.metadata.model_dump(),
            })
            consume_budget(user.id, estimated)
        except Exception as exc:
            logger.exception("streaming query failed")
            yield _sse({"type": "error", "detail": str(exc)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        #disable proxy/browser buffering so events flush as they're produced
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


#called after the ui shows the user a pending_sql block and they approve/reject it.
#resumes the graph run that's paused at request_sql_approval in app/core/graph.py.
#path must stay /query/sql/execute - the streamlit ui posts there (scripts/streamlit_app.py)
@router.post("/query/sql/execute", response_model=ChatResponse)
def approve_query(
    body: SQLApprovalRequest,
    user: User = Depends(get_current_user),
) -> ChatResponse:
    config = {"configurable": {"thread_id": body.query_id}}

    if graph.get_state(config).values == {}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending query found for this query_id",
        )

    result = graph.invoke(Command(resume={"approved": body.approved}), config=config)
    response = _response_from_state(result, body.query_id)

    if response.pending_sql is None:
        out_allowed, redacted, _ = moderate_and_redact(response.answer)
        if not out_allowed:
            raise HTTPException(status_code=500, detail="output_blocked")
        response.answer = redacted

    return response
