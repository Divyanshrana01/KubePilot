# Pydantic models

import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator

#these regex patterns catch common tricks people use to hijack the AI. this is a cheap
#first-pass filter at the schema layer; the heavier llm-guard pipeline in app/security
#does the real injection/moderation scanning once the request reaches the route.
_INJECTION_PATTERNS = [
    r"(?i)(ignore\s+previous|ignore\s+above|forget\s+your\s+instructions)",
    r"(?i)(system\s*prompt|reveal\s+your\s+instructions|show\s+your\s+prompt)",
    r"(?i)(you\s+are\s+now|new\s+instructions|override\s+previous)",
    r"(?i)(<\s*script|javascript:|on\w+\s*=)",
]


#shared validator for any free-text field a user sends in: strips it, rejects empty or
#symbol-only input, and blocks the obvious prompt-injection patterns above.
def reject_unsafe_text(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Text cannot be empty or whitespace only")

    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, v):
            raise ValueError("Text contains potentially malicious content")

    #reject input that is only symbols/punctuation with no real words
    if re.match(r"^[\W_]+$", v):
        raise ValueError("Text must contain actual content")

    return v


#a small preview of a retrieved chunk, used inside the response metadata
class RetrievedChunkPreview(BaseModel):
    text: str
    source: str
    score: float = 0.0

#extra info we attach to every response so the caller knows what happened internally
class ResponseMetadata(BaseModel):
    route: str = "rag"
    retrieved_chunks: list[RetrievedChunkPreview] = Field(default_factory=list)
    cache_hit: bool = False
    crag_triggered: bool = False
    crag_relevance_score: float | None = None
    reflection_iterations: int = 0  #how many regenerate-and-reflect loops actually ran
    reflection_score: float | None = None
    refined_question: str | None = None  #the reformulated question, if reflection rewrote it
    executed_sql: str | None = None  #the SQL generated/run on the sql route, surfaced to the UI


#when the system wants to run SQL, it stores it here until the user approves it
class PendingSQLBlock(BaseModel):
    sql: str
    query_id: str
    explanation: str = ""


#body for the /query/approve endpoint, used to resume a graph run that's paused on
#a pending sql block. query_id is the thread_id handed back in that PendingSQLBlock
class SQLApprovalRequest(BaseModel):
    query_id: str
    approved: bool


#this is what the API sends back to the user after processing their question
class ChatResponse(BaseModel):
    answer: str = Field(..., min_length=0)
    sources: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    pending_sql: PendingSQLBlock | None = None
    cache_hit: bool = False
    cost_saved: str = "$0.00"
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata)

#this is the request body for the /query endpoint (direct RAG query with flags)
class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User question",
    )
    top_k: int = Field(default=5, ge=1, le=50)
    enable_hyde: bool = False
    search_mode: Literal["dense", "sparse", "hybrid"] = "dense"
    enable_rerank: bool | None = None
    enable_crag: bool = True
    enable_self_reflective: bool = False  #opt-in: adds reflect-and-retry loop, costs extra LLM calls

    #reuse the shared free-text validator (strip, reject empty/symbol-only, block injections)
    @field_validator("question")
    @classmethod
    def validate_question_content(cls, v: str) -> str:
        return reject_unsafe_text(v)


#a single chunk of text that was pulled from the vector store
class RetrievedChunk(BaseModel):
    text: str
    source: str
    score: float = 0.0
    
    
    
#the grader's verdict on how relevant a retrieved chunk is, used by the CRAG flow
class CRAGEvaluation(BaseModel):
    relevance_score: float = 0.0
    relevance_label: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    

class ReflectionResult(BaseModel):
    """Self-RAG reflection on a generated answer (checks if the answer is good enough or needs redoing)."""

    reflection_score: float = 0.0
    needs_regeneration: bool = False
    refined_question: str = ""
    reasoning: str = ""


