from __future__ import annotations

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    text: str
    source: str = ""
    score: float = 0.0


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []
