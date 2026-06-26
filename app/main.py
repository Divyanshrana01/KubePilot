from loguru import logger
from fastapi import FastAPI
from app.api import admin, auth, query

#create the main fastapi app and register all the route groups
app = FastAPI(title="Adv_RAG", version="1.0.0")
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(query.router)


#the llm-guard scanners (prompt injection, toxicity, ban-topics, pii) lazy-load their
#models on first use. left alone, that multi-hundred-MB download/load happens inside
#a user's first /query request and can blow past any reasonable client timeout.
#running it once here, at container startup, pays that cost before traffic arrives.
@app.on_event("startup")
async def _warm_up_guard_models() -> None:
    from app.security.content_moderation import moderate_and_redact
    from app.security.input_guard import check_input_safe

    logger.info("Warming up llm-guard scanner models...")
    try:
        check_input_safe("warmup")
        moderate_and_redact("warmup")
        logger.info("llm-guard scanner models warmed up")
    except Exception:
        logger.exception("llm-guard warmup failed; first real request will pay the cost instead")