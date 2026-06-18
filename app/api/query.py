from app.config import settings
from fastapi import APIRouter, Depends, HTTPException

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
    return run_rag(body.question, flags={"top_k": body.top_k, "search_mode": body.search_mode})