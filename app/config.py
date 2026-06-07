from pydantic_settings import BaseSettings, SettingsConfigDict


class settings(BaseSettings):
    """App settings"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    openai_api_key: str = ""
    llm_model_answer: str = "gpt-4o"
    llm_model_grader: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    
    qdrant_url: str = "https://localhost:6333"
    qdrant_collection_name: str = "documents"
    
    database_url: str = "postgres://postgres:postgres@localhost:5432/adv_rag"
    
    upstash_redis_url: str = "https://flowing-grub-113529.upstash.io"
    upstash_redis_token: str = ""
    cache_ttl_embeddings: int = 604800  # 7 days
    cache_ttl_rag: int = 3600           # 1 hour
    cache_ttl_sql_gen: int = 86400      # 24 hours
    cache_ttl_sql_result: int = 3600    # 15 min
    cache_ttl_intent: int = 86400       # 24 hours
    
    storage_bucket_name: str = "ADV_RAG_CACHE"
    s3_cache_bucket: str = "ADV_RAG_CACHE"
    aws_region: str = "us-east-1"
    
    tavily_api_key: str = ""
    
    jwt_secret_key: str = ""
    jwt_expiration_minutes: int = 60
    
    rate_limit_requests: int = 20
    rate_limit_time_window_seconds: int = 60  # in seconds
    max_tokens_per_user_per_day: int = 100000
    auth_login_rate_limit: str = "5/minute"  # 5 login attempts per minute
    auth_register_rate_limit_per_hour: str = "3/hour"  # 3 registration attempts per hour
    
    max_input_tokens: int = 3_000
    reserved_context_tokens: int = 1_000
    reserved_output_tokens: int = 1_000
    
    prompt_injection_threshold: float = 0.75
    toxicity_threshold: float = 0.75
    output_toxicity_threshold: float = 0.5
    max_validation_retries: int = 2
    hyde_num_hypotheses: int = 3
    hyde_enabled_by_default: bool = False
    hybrid_search_enabled: bool = True
    rrf_k: int = 60
    reranker_backend: str = "local"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    voyage_api_key: str = ""
    voyage_model: str = "rerank-2.5"
    reranker_initial_top_k: int = 20
    reranking_enabled_by_default: bool = True
    crag_relevance_threshold: float = 0.7
    crag_ambiguous_threshold: float = 0.5
    crag_enabled_by_default: bool = True
    reflection_min_score: float = 0.85
    max_reflection_retries: int = 2
    self_reflective_enabled_by_default: bool = False
    
    vanna_model: str = "gpt-4o"
    vanna_temperature: float = 0.0
    vanna_seed: int = 42
    
    log_json: bool = False
    log_level:str = "INFO"
    
    
settings = settings()