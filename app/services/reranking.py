import logging
import threading
import time
from typing import cast

from app.config import settings
from app.models import RetrievedChunk

logger = logging.getLogger(__name__)


#blocks just long enough between calls to stay under voyage's free-tier rpm cap,
#shared across Reranker instances since the rpm limit is per api key, not per object
class _RateLimiter:
    def __init__(self, calls_per_minute: int) -> None:
        self._min_interval = 60.0 / calls_per_minute
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()


_voyage_rate_limiter = _RateLimiter(settings.voyage_rerank_rpm)


#reorders chunks already pulled by the vector/sparse search using a smarter model
#that actually reads (query, chunk) pairs together, instead of just comparing embeddings
class Reranker:
    def __init__(self) -> None:
        self.backend = settings.reranker_backend
        self._local_model: object | None = None
        self._voyage_client: object | None = None

    #loads the cross-encoder model once and reuses it, since loading is slow
    def _load_local_model(self) -> object:
        if self._local_model is None:
            from sentence_transformers import CrossEncoder

            self._local_model = CrossEncoder(settings.reranker_model)
        return self._local_model

    #loads the voyage api client once, fails fast if no api key is configured
    def _load_voyage_client(self) -> object:
        if self._voyage_client is None:
            import voyageai

            if not settings.voyage_api_key:
                raise ValueError("Voyage API key is required for voyage reranker backend")
            self._voyage_client = voyageai.Client(api_key=settings.voyage_api_key)
        return self._voyage_client

    #main entry point: pick local or voyage backend, rerank, and if anything blows up
    #just fall back to returning the chunks in their original order instead of erroring out
    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []

        top_k = top_k or settings.reranker_initial_top_k
        top_k = min(top_k, len(chunks))

        try:
            if self.backend == "voyage":
                return self._rerank_voyage(query, chunks, top_k)
            return self._rerank_local(query, chunks, top_k)
        except Exception:
            logger.exception("Reranking failed, returning original order")
            return chunks[:top_k]


    #scores every (query, chunk) pair with the local cross-encoder model and
    #sorts chunks by that new score, keeping only the top_k best
    def _rerank_local(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        model = self._load_local_model()
        pairs = [[query, chunk.text] for chunk in chunks]
        scores = cast("list[float]", model.predict(pairs))

        scored = [
            RetrievedChunk(text=chunk.text, source=chunk.source, score=float(score))
            for chunk, score in zip(chunks, scores, strict=True)
        ]
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]


    #same idea as _rerank_local but sends the work to voyage's hosted rerank api instead
    #of running a model locally; voyage returns the original index of each result so we
    #can map its scores back onto our RetrievedChunk objects
    def _rerank_voyage(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        client = self._load_voyage_client()
        documents = [chunk.text for chunk in chunks]
        _voyage_rate_limiter.wait()
        result = client.rerank(
            query=query,
            documents=documents,
            model=settings.voyage_model,
            top_k=top_k,
        )

        # Map results back to RetrievedChunk
        reranked: list[RetrievedChunk] = []
        for item in result.results:
            idx = item.index
            chunk = chunks[idx]
            reranked.append(
                RetrievedChunk(
                    text=chunk.text,
                    source=chunk.source,
                    score=float(item.relevance_score),
                )
            )
        return reranked
