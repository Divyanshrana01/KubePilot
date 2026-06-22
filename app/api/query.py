from fastapi import APIRouter, Depends

from app.middleware.auth import User, get_current_user
from app.models import ChatResponse, QueryRequest
from app.services.rag_service import run_rag


router = APIRouter(tags=["query"])

#main endpoint the ui calls to ask a question, needs a logged in user, just forwards to run_rag
@router.post("/query",response_model=ChatResponse)
async def query(
    body: QueryRequest,
    user: User = Depends(get_current_user),
) -> ChatResponse:
    flags = {"top_k": body.top_k, "search_mode": body.search_mode, "hyde": body.enable_hyde, "enable_crag":body.enable_crag}
    if body.enable_rerank is not None:
        flags["rerank"] = body.enable_rerank
    return run_rag(body.question, flags=flags)