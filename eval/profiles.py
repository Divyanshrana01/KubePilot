from __future__ import annotations

#each profile is a named combination of feature flags.
#we pass these into the RAG pipeline to test how each feature improves results.
#the eval harness picks a profile by name from the command line (e.g. --profile hybrid+rerank).
PROFILES: dict[str, dict] = {
    #naive: plain dense search, no extra features, this is the baseline to beat
    "naive":{
        "search_mode": "dense",
        "enable_hyde": False,
        "enable_rerank": False,
        "enable_crag": False,
        "enable_self_reflective": False,
        "top_k": 5,
    },
    #sparse_only: only uses keyword-based TF-IDF search, no embeddings
    "sparse_only": {
        "search_mode": "sparse",
        "enable_hyde": False,
        "enable_rerank": False,
        "enable_crag": False,
        "enable_self_reflective": False,
        "top_k": 5,
    },
    #hybrid: combines dense + sparse search using RRF fusion
    "hybrid": {
        "search_mode": "hybrid",
        "enable_hyde": False,
        "enable_rerank": False,
        "enable_crag": False,
        "enable_self_reflective": False,
        "top_k": 5,
    },
    #hybrid+rerank: hybrid search then reranks the top results with a cross-encoder
    "hybrid+rerank": {
        "search_mode": "hybrid",
        "enable_hyde": False,
        "enable_rerank": True,
        "enable_crag": False,
        "enable_self_reflective": False,
        "top_k": 5,
    },
    #hybrid+rerank+hyde: also generates fake answers first to expand the query before searching
    "hybrid+rerank+hyde": {
        "search_mode": "hybrid",
        "enable_hyde": True,
        "enable_rerank": True,
        "enable_crag": False,
        "enable_self_reflective": False,
        "top_k": 5,
    },
    #hybrid+rerank+crag: also checks if retrieved chunks are actually relevant before answering
    "hybrid+rerank+crag": {
        "search_mode": "hybrid",
        "enable_hyde": False,
        "enable_rerank": True,
        "enable_crag": True,
        "enable_self_reflective": False,
        "top_k": 5,
    },
    #all: every feature on at the same time, the maximum quality profile
    "all": {
        "search_mode": "hybrid",
        "enable_hyde": True,
        "enable_rerank": True,
        "enable_crag": True,
        "enable_self_reflective": True,
        "top_k": 5,
    },
}