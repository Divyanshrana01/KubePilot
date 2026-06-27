from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import admin, auth, query
from app.config import settings


#the llm-guard scanners (prompt injection, toxicity, ban-topics, pii) lazy-load their
#models on first use. left alone, that multi-hundred-MB download/load happens inside
#a user's first /query request and can blow past any reasonable client timeout.
#running it once here, at startup, pays that cost before traffic arrives.
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.security.content_moderation import moderate_and_redact
    from app.security.input_guard import check_input_safe

    logger.info("Warming up llm-guard scanner models...")
    try:
        check_input_safe("warmup")
        moderate_and_redact("warmup")
        logger.info("llm-guard scanner models warmed up")
    except Exception:
        logger.exception("llm-guard warmup failed; first real request will pay the cost instead")

    #the cross-encoder reranker lazy-loads its model on first use; preload it here so the
    #first reranked query isn't the one that pays the load cost.
    try:
        from app.services.rag_service import _reranker

        _reranker.warm()
        logger.info("reranker model warmed up")
    except Exception:
        logger.exception("reranker warmup failed; first reranked request will pay the cost instead")

    #the BM25 sparse index is built by scrolling the whole Qdrant collection (~10k docs);
    #build it once here so the first sparse/hybrid query doesn't pay that multi-second cost.
    try:
        from app.services.vector_store import get_sparse_index

        get_sparse_index()
        logger.info("BM25 sparse index warmed up")
    except Exception:
        logger.exception("sparse index warmup failed; first hybrid/sparse request will pay the cost")
    yield


#create the main fastapi app and register all the route groups
app = FastAPI(title="Adv_RAG", version="1.0.0", lifespan=lifespan)

#allow the react frontend (a separate browser origin) to call this api. without this,
#the browser blocks every cross-origin request before it ever reaches our routes.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(query.router)
