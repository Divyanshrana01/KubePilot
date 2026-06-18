import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator

#this is what the user sends in when they want to chat with the AI.
#the validator below blocks empty messages and common prompt injection attacks.
class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User message to the AI assistant",
    )
    @field_validator("message")
    @classmethod
    def validate_message_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty or whitespace only")

        #these regex patterns catch common tricks people use to hijack the AI
        injection_patterns = [
            r"(?i)(ignore\s+previous|ignore\s+above|forget\s+your\s+instructions)",
            r"(?i)(system\s*prompt|reveal\s+your\s+instructions|show\s+your\s+prompt)",
            r"(?i)(you\s+are\s+now|new\s+instructions|override\s+previous)",
            r"(?i)(<\s*script|javascript:|on\w+\s*=)",
        ]

        for pattern in injection_patterns:
            if re.search(pattern, v):
                raise ValueError("Message contains potentially malicious content")

        #reject messages that are only symbols/punctuation with no real words
        if re.match(r"^[\W_]+$", v):
            raise ValueError("Message must contain actual text content")

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


#when the system wants to run SQL, it stores it here until the user approves it
class PendingSQLBlock(BaseModel):
    sql: str
    query_id: str
    explanation: str = ""


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
    search_mode: Literal["dense", "sparse", "hybrid"] = "dense"

    #same injection check as ChatRequest but for the question field
    @field_validator("question")
    @classmethod
    def validate_question_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty or whitespace only")

        injection_patterns = [
            r"(?i)(ignore\s+previous|ignore\s+above|forget\s+your\s+instructions)",
            r"(?i)(system\s*prompt|reveal\s+your\s+instructions|show\s+your\s+prompt)",
            r"(?i)(you\s+are\s+now|new\s+instructions|override\s+previous)",
            r"(?i)(<\s*script|javascript:|on\w+\s*=)",
        ]
        for pattern in injection_patterns:
            if re.search(pattern, v):
                raise ValueError("Question contains potentially malicious content")

        if re.match(r"^[\W_]+$", v):
            raise ValueError("Question must contain actual text content")

        return v


#a single chunk of text that was pulled from the vector store
class RetrievedChunk(BaseModel):
    text: str
    source: str
    score: float = 0.0