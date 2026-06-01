from fastapi import FastAPI
from app.api import admin, auth

app = FastAPI(title="Adv_RAG", version="1.0.0")
app.include_router(admin.router)
app.include_router(auth.router)