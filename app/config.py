from pydantic_settings import BaseSettings, SettingsConfigDict

#this class holds all the config for the whole app.
#pydantic reads these values from the .env file automatically.
class settings(BaseSettings):
    """App settings"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    #openai keys and which models to use for answering vs grading
    openai_api_key: str = ""
    llm_model_answer: str = "gpt-4o"
    llm_model_grader: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    #qdrant vector db connection settings
    qdrant_url: str = "https://localhost:6333"
    qdrant_collection_name: str = "documents"

    #postgres database connection string
    database_url: str = "postgres://postgres:postgres@localhost:5432/adv_rag"

    #redis cache settings — how long each type of result gets stored
    upstash_redis_url: str = "https://flowing-grub-113529.upstash.io"
    upstash_redis_token: str = ""
    cache_ttl_embeddings: int = 604800  # 7 days
    cache_ttl_rag: int = 3600           # 1 hour
    cache_ttl_sql_gen: int = 86400      # 24 hours
    cache_ttl_sql_result: int = 3600    # 15 min
    cache_ttl_intent: int = 86400       # 24 hours

    #s3 bucket for storing cached files
    storage_bucket_name: str = "ADV_RAG_CACHE"
    s3_cache_bucket: str = "ADV_RAG_CACHE"
    aws_region: str = "us-east-1"

    #tavily is the web search provider for fallback queries
    tavily_api_key: str = ""

    #jwt settings for user auth tokens
    jwt_secret_key: str = ""
    jwt_expiration_minutes: int = 60

    #rate limiting — how many requests per user per time window
    rate_limit_requests: int = 20
    rate_limit_time_window_seconds: int = 60  # in seconds
    max_tokens_per_user_per_day: int = 100000
    auth_login_rate_limit: str = "5/minute"  # 5 login attempts per minute
    auth_register_rate_limit_per_hour: str = "3/hour"  # 3 registration attempts per hour

    #token budget controls — limit how big the input can be
    max_input_tokens: int = 3_000
    reserved_context_tokens: int = 1_000
    reserved_output_tokens: int = 1_000

    #security thresholds — if a score is above these, reject the input/output
    prompt_injection_threshold: float = 0.75
    toxicity_threshold: float = 0.75
    output_toxicity_threshold: float = 0.5
    max_validation_retries: int = 2

    #hyde settings — generate fake answers to improve search
    hyde_num_hypotheses: int = 3
    hyde_enabled_by_default: bool = False

    #hybrid search uses both dense and sparse vectors together
    hybrid_search_enabled: bool = True
    rrf_k: int = 60

    #reranker settings — used to re-score retrieved chunks
    reranker_backend: str = "local"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    voyage_api_key: str = ""
    voyage_model: str = "rerank-2.5"
    reranker_initial_top_k: int = 20
    reranking_enabled_by_default: bool = True

    #crag settings — corrective rag checks if retrieved chunks are relevant
    crag_relevance_threshold: float = 0.7
    crag_ambiguous_threshold: float = 0.5
    crag_enabled_by_default: bool = True

    #self-reflection settings — the model grades its own answer and retries if needed
    reflection_min_score: float = 0.85
    max_reflection_retries: int = 2
    self_reflective_enabled_by_default: bool = False

    #vanna is used for text-to-sql generation
    vanna_model: str = "gpt-4o"
    vanna_temperature: float = 0.0
    vanna_seed: int = 42

    #logging settings
    log_json: bool = False
    log_level:str = "INFO"


#create the single shared settings object that all other files import
settings = settings()