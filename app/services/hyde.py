# HyDE (Hypothetical Document Embeddings): instead of searching with the raw question,
# we ask the LLM to write a fake "ideal answer" first, then search using that text.
# The idea is that a plausible answer is closer in meaning to real documents than a short question.

import re
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.models import RetrievedChunk
from app.services.embedding_service import embed_texts
from app.services.llm_service import generate
from app.services.vector_store import search


_HYDE_SYSTEM_PROMPT = (
    "You are a helpful assistant. Given a user question, write a brief, plausible answer "
    "(2-3 sentences) that would help retrieve relevant documents. Write only the answer, "
    "no preamble."
)

def _normalize_text(text: str) -> str:
    """Normalize whitespace for deduplication."""
    return re.sub(r"\s+", " ", text.strip())

class HyDERetriever:
    """Retrieves documents by generating hypothetical answers first, then searching with those."""

    def __init__(self, num_hypotheses: int | None = None) -> None:
        self.num_hypotheses = num_hypotheses or settings.hyde_num_hypotheses

    def retrieve(self, question: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Generate hypothetical answers, embed them alongside the question, search with each, then merge and dedupe."""
        if not question or not question.strip():
            return []

        # The N hypotheses are independent, so generate them concurrently instead of in a
        # serial loop — this turns HyDE's cost from N sequential LLM round-trips into ~1.
        # They also use the cheaper/faster grader model: a hypothesis only needs to be a
        # plausible search probe, not a polished answer, so the flagship model is wasted here.
        def _one_hypothesis(_: int) -> str:
            try:
                response = generate(
                    system_prompt=_HYDE_SYSTEM_PROMPT,
                    user_message=question,
                    model=settings.llm_model_grader,
                    temperature=0.7,
                )
                return response.get("text", "").strip()
            except Exception:
                # If generating a hypothesis fails, just skip it and keep going.
                return ""

        with ThreadPoolExecutor(max_workers=self.num_hypotheses) as pool:
            hypotheses = [h for h in pool.map(_one_hypothesis, range(self.num_hypotheses)) if h]

        # Always include the raw question itself as one of the search texts,
        # in case the hypotheses turn out to be off-base.
        all_texts = hypotheses + [question]

        if not all_texts:
            return []

        embeddings = embed_texts(all_texts)

        all_results: list[RetrievedChunk] = []

        for embedding in embeddings:
            try:
                results = search(embedding, top_k=top_k)
                all_results.extend(results)
            except Exception:
                # Skip failed searches rather than aborting the whole retrieval.
                continue

        # Different hypotheses may retrieve the same chunk; keep only the
        # highest-scoring version of each duplicate (matched by normalized text).
        deduped: dict[str, RetrievedChunk] = {}

        for chunk in all_results:
            key = _normalize_text(chunk.text)
            if key not in deduped or chunk.score > deduped[key].score:
                deduped[key] = chunk

        merged = sorted(deduped.values(), key=lambda c: c.score, reverse=True)
        return merged[:top_k]

