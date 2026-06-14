from fastapi import FastAPI
from app.api import admin, auth

#create the main fastapi app and register all the route groups
app = FastAPI(title="Adv_RAG", version="1.0.0")
app.include_router(admin.router)
app.include_router(auth.router)