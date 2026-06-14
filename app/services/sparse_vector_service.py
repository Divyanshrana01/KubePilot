import threading

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models import RetrievedChunk

#this class builds a TF-IDF index over a set of documents so we can do keyword-based search.
#TF-IDF gives higher scores to words that appear a lot in a chunk but rarely in other chunks.
class SparseVectorIndex:
    def __init__(self) -> None:
        #stop_words="english" removes common words like "the", "is", "and" that aren't useful
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.documents: list[dict] = []
        self.matrix = None
        self._lock = threading.RLock()

    #this fn takes the list of documents and fits the tfidf vectorizer on all their texts.
    #after this the matrix holds a sparse vector for every document ready to be searched.
    def fit(self, documents: list[dict]) -> None:
        with self._lock:
            self.documents = documents
            if not documents:
                self.matrix = None
                return

            texts = [doc.get("text", "") for doc in documents]
            try:
                self.matrix = self.vectorizer.fit_transform(texts)
            except ValueError:
                self.matrix = None
                return

            #if no useful vocabulary was found (all stopwords etc), set matrix to None
            if self.matrix.shape[1] == 0:
                self.matrix = None

    #this fn takes a query string and returns the top-k most similar chunks using cosine similarity.
    #it converts the query to a tfidf vector and compares it against all document vectors.
    def search(self, query: str, top_k: int = 20) -> list[RetrievedChunk]:
        """Return top-k chunks by TF-IDF cosine similarity."""
        with self._lock:
            if self.matrix is None or len(self.documents) == 0:
                return []

            query_vec = self.vectorizer.transform([query])
            similarities = cosine_similarity(query_vec, self.matrix).flatten()
            #sort descending and take the top_k indices
            top_indices = similarities.argsort()[::-1][:top_k]

            results: list[RetrievedChunk] = []
            for idx in top_indices:
                score = float(similarities[idx])
                #skip chunks that have zero similarity — they share no keywords with the query
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
            #rrf formula: 1 / (k + rank + 1) — higher rank = higher score
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank + 1)
            if key not in meta:
                meta[key] = {"text": chunk.text, "source": chunk.source}

    #sort by fused score descending and return as RetrievedChunk objects
    return [
        RetrievedChunk(text=text, source=meta[text]["source"], score=score)
        for text, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ]
    