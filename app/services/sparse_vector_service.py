import re
import threading

from rank_bm25 import BM25Okapi

from app.models import RetrievedChunk

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


#this class builds a BM25 index over a set of documents so we can do keyword-based search.
#BM25 scores terms like TF-IDF but with saturation for repeated terms and
#normalization for document length, which is why it's the standard for sparse retrieval.
class SparseVectorIndex:
    def __init__(self) -> None:
        self.bm25: BM25Okapi | None = None
        self.documents: list[dict] = []
        self._lock = threading.RLock()

    #this fn takes the list of documents and builds a bm25 index over their tokenized texts.
    def fit(self, documents: list[dict]) -> None:
        with self._lock:
            self.documents = documents
            if not documents:
                self.bm25 = None
                return

            tokenized = [_tokenize(doc.get("text", "")) for doc in documents]
            if not any(tokenized):
                self.bm25 = None
                return

            self.bm25 = BM25Okapi(tokenized)

    #this fn takes a query string and returns the top-k highest scoring chunks by bm25.
    def search(self, query: str, top_k: int = 20) -> list[RetrievedChunk]:
        """Return top-k chunks by BM25 score."""
        with self._lock:
            if self.bm25 is None or len(self.documents) == 0:
                return []

            scores = self.bm25.get_scores(_tokenize(query))
            #sort descending and take the top_k indices
            top_indices = scores.argsort()[::-1][:top_k]

            results: list[RetrievedChunk] = []
            for idx in top_indices:
                score = float(scores[idx])
                #skip chunks that have zero score, they share no keywords with the query
                if score <= 0:
                    continue
                doc = self.documents[idx]
                results.append(
                    RetrievedChunk(
                        text=doc.get("text", ""),
                        source=doc.get("source", ""),
                        score=score,
                    )
                )
            return results

#this fn merges results from multiple ranked lists (e.g. dense + sparse) using RRF.
#RRF works by giving each chunk a score based on its rank position in each list,
#then summing those scores across all lists. chunks that rank high in multiple lists win.
def fuse_rrf(
    result_lists: list[list[RetrievedChunk]],
    rrf_k: int = 60,
) -> list[RetrievedChunk]:
    """Fuse multiple ranked result lists using Reciprocal Rank Fusion."""
    scores: dict[str, float] = {}
    meta: dict[str, dict] = {}

    for result_list in result_lists:
        for rank, chunk in enumerate(result_list):
            key = chunk.text
            #rrf formula: 1 / (k + rank + 1), higher rank means higher score
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank + 1)
            if key not in meta:
                meta[key] = {"text": chunk.text, "source": chunk.source}

    #sort by fused score descending and return as RetrievedChunk objects
    return [
        RetrievedChunk(text=text, source=meta[text]["source"], score=score)
        for text, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ]
    