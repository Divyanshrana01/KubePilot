import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.types import Command

from app.config import settings
from app.core.graph import graph
from app.middleware.auth import User, get_current_user
from app.middleware.rate_limiter import is_allowed_user
from app.models import ChatResponse, PendingSQLBlock, QueryRequest, SQLApprovalRequest
from app.security.content_moderation import moderate_and_redact
from app.security.input_guard import check_input_safe
from app.security.input_restructuring import count_tokens, restructure_input
from app.security.token_budget import check_budget, consume_budget

router = APIRouter(tags=["query"])


#rough total-token estimate for the budget check: the question itself plus headroom for the reply
def _estimate_tokens(question: str) -> int:
    return count_tokens(question) + settings.reserved_output_tokens


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
@router.post("/query", response_model=ChatResponse)
async def query(
    body: QueryRequest,
    user: User = Depends(get_current_user),
) -> ChatResponse:
    #layer: per-user sliding-window rate limit
    allowed, _, _ = is_allowed_user(
        user.id,
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_time_window_seconds,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    #layer: per-user per-day token budget, checked before spending any llm calls
    estimated = _estimate_tokens(body.question)
    ok, remaining = check_budget(user.id, estimated)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You have {remaining} tokens remaining today; "
                f"this request estimated to use {estimated}."
            ),
        )

    #layer: truncate/summarize if the question alone is too long for the model's input limit
    restructured, _method = restructure_input(body.question)

    #layer: llm-guard input scan for injection / banned topics / toxicity
    guard_allowed, guard_reason = check_input_safe(restructured)
    if not guard_allowed:
        raise HTTPException(status_code=400, detail=f"injection_blocked: {guard_reason}")

    #layer: redact pii and check for blocked content in the question itself
    mod_allowed, moderated_in, mod_reason = moderate_and_redact(restructured)
    if not mod_allowed:
        raise HTTPException(status_code=400, detail=f"content_blocked: {mod_reason}")

    #keys here have to match what _flag()/_cache_context() in rag_service.py expect
    #("hyde"/"rerank", not "enable_hyde"/"enable_rerank") or those flags get silently ignored
    flags = {
        "top_k": body.top_k,
        "search_mode": body.search_mode,
        "hyde": body.enable_hyde,
        "enable_crag": body.enable_crag,
        "enable_self_reflective": body.enable_self_reflective,
    }
    if body.enable_rerank is not None:
        flags["rerank"] = body.enable_rerank

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


#called after the ui shows the user a pending_sql block and they approve/reject it.
#resumes the graph run that's paused at request_sql_approval in app/core/graph.py
@router.post("/query/approve", response_model=ChatResponse)
async def approve_query(
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
