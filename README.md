# Enterprise Advanced RAG - Kubernetes SRE Copilot

> Production-grade RAG system for Kubernetes IT operations.
> LangGraph orchestration, hybrid search, HyDE, CRAG, Self-RAG, Text2SQL with human approval, 9-layer guardrails, and RAGAS evaluation.

---

## What This Is

An end-to-end AI copilot for Kubernetes SRE workflows. Ask natural-language questions about your cluster incidents, pod failures, runbooks, and live metrics. The system routes queries through a LangGraph state machine to either a multi-stage RAG pipeline or a schema-aware Text2SQL pipeline, with a human-in-the-loop approval gate before any database query executes.

Built incrementally across 7 phases. Every advanced RAG technique earns its place - each phase adds measurable RAGAS improvement before moving on.

---

## Architecture

```
SRE / User (HTTPS + JWT Bearer)
        |
   FastAPI Service
   REST + OpenAI + Streamlit UI
        |
   9-Layer Input Security Pipeline
   (Pydantic, JWT, Rate Limit, Token Budget, llm-guard, PII Redaction)
        |
   5-Tier Redis Cache (Upstash)
   Embedding TTL 7d | Intent TTL 24h | SQL Gen TTL 24h | SQL Result TTL 15m | RAG Answer TTL 1h
        |
   LangGraph State Machine
   (Postgres-checkpointed, conditional edges, interrupt() for human-in-the-loop)
        |
   Intent Router -> rag / sql / hybrid
        |
   +---------------------------+---------------------------+
   |   RAG Pipeline            |   Text2SQL Pipeline       |
   |   HyDE (3 hyp. answers)   |   Generate SQL (GPT-4o)   |
   |   Embed Query             |   Validate SQL            |
   |   Hybrid Retrieval        |   interrupt() - HITL      |
   |   RRF (k=60)              |   Execute SQL             |
   |   Cross-Encoder Rerank    |   Format Results          |
   |   CRAG Grader             |                           |
   |   Spotlighting (L8)       |                           |
   +---------------------------+---------------------------+
        |
   LLM Answer Generation (GPT-4o, grounded on spotlighted context)
   Self-RAG Reflect (score < 0.8 -> re-retrieve, max 2)
        |
   Finalize + attach metadata
        |
   Output Security Pipeline
   (Output Moderation + PII Redaction, Pydantic Schema Validation)
        |
   ChatResponse -> User
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI, OpenAI SDK, StreamlitUI |
| Orchestration | LangGraph, LangChain |
| Vector store | Qdrant (dense + sparse hybrid collection, ~10k chunks) |
| Relational DB | PostgreSQL 16 (ops DB + LangGraph checkpoints) |
| Caching | Upstash Redis (5-tier, SHA-256 keys, per-tier TTL) |
| Embeddings | text-embedding-3-small |
| LLM | GPT-4o |
| Reranking | BGE / Voyage AI cross-encoder |
| Web fallback | Tavily API |
| Raw corpus | S3 / Local FS (K8s docs + 95% noise PDFs) |
| Evaluation | RAGAS |
| Security | Pydantic v2, PyJWT, llm-guard, tiktoken |
| Infra | Docker, AWS ECS Fargate |

---

## What You Will Learn

- Advanced RAG design patterns (HyDE, CRAG, Self-RAG)
- Hybrid search: dense + BM25 sparse vectors, RRF fusion
- Cross-encoder reranking with BGE / Voyage AI
- LangGraph state machine orchestration with Postgres checkpointing
- Text2SQL with schema-aware prompting and SQL AST validation
- Human-in-the-loop approval gates using LangGraph `interrupt()`
- 5-tier Redis caching strategy keyed on SHA-256 query hashes
- 9-layer defense-in-depth guardrails pipeline
- RAGAS evaluation: faithfulness, answer relevancy, context precision, context recall
- Production deployment: Dockerized, AWS ECS Fargate, GitHub Actions CI/CD

---

## Project Structure

```
enterprise-rag/
├── api/
│   ├── main.py                  # FastAPI app, routes, middleware chain
│   ├── auth.py                  # JWT middleware (L4a)
│   ├── rate_limit.py            # Redis sliding window rate limiter (L4b)
│   └── schemas.py               # Pydantic request/response models (L1, L9)
├── guardrails/
│   ├── input_pipeline.py        # L1 -> L7a: injection, token budget, PII
│   └── output_pipeline.py       # L7b -> L9: output moderation, schema validate
├── graph/
│   ├── state.py                 # LangGraph state definition
│   ├── router.py                # Intent router node
│   ├── rag_pipeline.py          # HyDE, embed, hybrid retrieve, RRF, rerank
│   ├── crag.py                  # CRAG grader + Tavily fallback node
│   ├── spotlighting.py          # XML chunk wrapping (L8)
│   ├── self_rag.py              # Reflect node + retry loop
│   ├── text2sql.py              # SQL gen, validate, interrupt, execute
│   └── graph.py                 # Full LangGraph compile + checkpointer
├── retrieval/
│   ├── qdrant_client.py         # Hybrid collection setup, upsert, search
│   ├── embedder.py              # text-embedding-3-small wrapper + cache
│   └── rrf.py                   # Reciprocal Rank Fusion implementation
├── cache/
│   └── redis_cache.py           # 5-tier cache: TTL config, SHA-256 keying
├── ingest/
│   ├── chunker.py               # K8s doc chunking strategy
│   ├── embedder.py              # Batch embed + upsert to Qdrant
│   └── dedup.py                 # SHA-256 content deduplication
├── eval/
│   ├── ragas_eval.py            # RAGAS evaluation harness
│   └── golden_dataset.json      # 50 K8s incident Q&A pairs
├── ui/
│   └── app.py                   # Streamlit UI + SQL approval interface
├── tests/
│   ├── test_guardrails.py
│   ├── test_retrieval.py
│   └── test_graph.py
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Build Phases

### Phase 1 - Baseline RAG + Infra (Week 1-2)

FastAPI service, Qdrant dense retrieval, PostgreSQL, Redis client, Streamlit stub. Nail the data layer before adding any advanced technique.

### Phase 2 - Hybrid Search + Reranking + HyDE (Week 2-3)

Qdrant sparse (BM25) + dense hybrid collection. RRF fusion at k=60. BGE cross-encoder reranks top-20. HyDE generates 3 hypothetical answers before embedding. Measure RAGAS delta before moving on.

### Phase 3 - CRAG + Spotlighting (Week 3-4)

LangGraph grader node scores each retrieved chunk. Score < 0.7 triggers Tavily web fallback. Chunks wrapped in `<doc id=N>` XML tags before LLM call. Context precision improves measurably.

### Phase 4 - Self-RAG Reflect Loop (Week 4-5)

Post-generation faithfulness score. Score < 0.8 triggers re-retrieval. Max 2 retries. Catches confident-but-wrong answers on novel K8s error patterns.

### Phase 5 - Text2SQL + Human-in-the-Loop (Week 5-6)

Intent router classifies queries as `rag / sql / hybrid`. GPT-4o with full schema in system prompt generates SQL. AST validator blocks non-SELECT. `interrupt()` pauses the graph and surfaces SQL to Streamlit for human approve/reject before execution.

### Phase 6 - 9-Layer Guardrails (Week 6-8)

Input pipeline: L1 injection detection, L4a JWT, L4b rate limit, L6 token budget, L5 restructure, L2 llm-guard, L7a PII redaction. Output pipeline: L7b post-generation moderation, L9 Pydantic schema validation with LLM retry on failure.

### Phase 7 - RAGAS Evals + Cache + Deploy (Week 8-10)

5-tier Redis cache wired on all expensive calls. RAGAS eval suite runs against 50 golden Q&A pairs. Dockerized services pushed to ECR. AWS ECS Fargate deployment via GitHub Actions.

---

## Setup

### Prerequisites

- Docker + Docker Compose
- Python 3.11+
- Qdrant Cloud account or local Qdrant instance
- Upstash Redis account
- OpenAI API key
- Tavily API key (for CRAG web fallback)

### Local dev

```bash
git clone https://github.com/<your-username>/enterprise-rag
cd enterprise-rag

cp .env.example .env
# Fill in: OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY,
#          REDIS_URL, DATABASE_URL, TAVILY_API_KEY, JWT_SECRET

docker-compose up -d          # starts Postgres + Qdrant local (if not using cloud)

pip install -r requirements.txt

python ingest/embedder.py     # chunk + embed K8s docs into Qdrant

uvicorn api.main:app --reload # FastAPI on :8000
streamlit run ui/app.py       # Streamlit UI on :8501
```

### Environment variables

```
OPENAI_API_KEY=
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION=k8s-sre
REDIS_URL=
DATABASE_URL=postgresql://...
TAVILY_API_KEY=
JWT_SECRET=
JWT_ALGORITHM=HS256
RATE_LIMIT_RPM=20
TOKEN_BUDGET_DAILY=100000
```

---

## Evaluation

RAGAS metrics tracked per phase against 50 golden K8s incident Q&A pairs:

| Metric | What it measures |
|---|---|
| Faithfulness | Answer grounded in retrieved context, no hallucination |
| Answer relevancy | Answer addresses the query |
| Context precision | Retrieved chunks actually relevant |
| Context recall | All needed information was retrieved |

Run evals:

```bash
python eval/ragas_eval.py --phase all
```

Baseline scores are measured first, then delta tracked for each technique added. No metric is invented.

---

## API

```
POST /query
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "query": "Why are pods in CrashLoopBackOff after the last deploy?",
  "mode": "auto"
}

Response:
{
  "answer": "...",
  "sources": [...],
  "route": "rag",
  "self_rag_score": 0.91,
  "cache_hit": false
}
```

```
GET /health
GET /metrics
POST /sql/approve  (HITL endpoint called by Streamlit)
```

---

## 5-Tier Cache Strategy

| Tier | Key | TTL | Saves |
|---|---|---|---|
| Embedding | SHA-256(text) | 7 days | text-embedding-3-small call |
| Intent | SHA-256(query) | 24 hours | GPT-4o intent classification |
| SQL Gen | SHA-256(query+schema) | 24 hours | GPT-4o SQL generation |
| SQL Result | SHA-256(sql) | 15 minutes | Postgres round-trip |
| RAG Answer | SHA-256(query+context) | 1 hour | Full pipeline |

---

## 9-Layer Guardrails

```
L1   Pydantic + regex         Injection pattern detection on raw input
L4a  JWT Auth                 PyJWT bearer token validation
L4b  Rate Limit               20 req/min per user, Redis sliding window
L6   Token Budget             100k tokens/day/user, tiktoken counting
L5   Input Restructure        Normalize, language detect, tiktoken truncate
L2   llm-guard Scan           Prompt injection + toxicity classification
L7a  Content Moderation       PII redaction (regex + NER) before LLM
L7b  Output Moderation        Post-generation PII scan
L9   Pydantic Schema Val.     Structured output validation, LLM retry on fail
```

---

## Hardware Notes

Developed and tested on RTX/GTX 1650 4GB + Ryzen 5 5600H.

For local reranking: use `cross-encoder/ms-marco-MiniLM-L-6-v2` instead of BGE-large to fit within 4GB VRAM. All LLM calls (GPT-4o, embeddings) go via API so GPU is used only for local reranker inference.

---

## License

MIT
