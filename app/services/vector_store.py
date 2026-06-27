from __future__ import annotations

import threading
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings
from app.models import RetrievedChunk



VECTOR_SIZE = 1536


def get_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, timeout=30)

#creates the qdrant collection if it doesnt exist yet, safe to call this every time before writing
def ensure_collection() -> None:
    client = get_client()
    existing = {c.name for c in client.get_collections().collections}

    if settings.qdrant_collection_name not in existing: # type: ignore
        client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

#this fn takes two parallel lists, one for our embeddings and one for our chunks, 
#its will map them both together and add it into the qdrant vector store.
def upsert_chunks(chunks: list[RetrievedChunk], embeddings: list[list[float]]) -> None:
    ensure_collection()
    client  = get_client()
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={"text": chunk.text, "source": chunk.source},
        )
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]
    client.upsert(collection_name=settings.qdrant_collection_name, points=points)

#plain dense search, sends the embedding to qdrant and gets back the closest chunks
def search(query_embedding: list[float], top_k: int = 5) -> list[RetrievedChunk]:
    client = get_client()
    results = client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=query_embedding,
        limit=top_k,
        with_payload=True,
    ).points

    return [
        RetrievedChunk(
            text=p.payload.get("text", ""),
            source=p.payload.get("source", ""),
            score=float(p.score),
        )
        for p in results
    ]


#pulls every chunk out of qdrant and builds a bm25 index over them for keyword search.
#this scrolls the whole collection (~10k docs) and tokenizes all of it, so it's expensive
#(~several seconds) - which is why the result is cached below instead of rebuilt per query.
def _build_sparse_index():
    from app.services.sparse_vector_service import SparseVectorIndex
    client = get_client()
    all_points, _next_page = client.scroll(
        collection_name=settings.qdrant_collection_name,
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )
    documents = [
        {
            "text": point.payload.get("text", "") if point.payload else "",
            "source": point.payload.get("source", "") if point.payload else "",
            "id": str(point.id),
        }
        for point in all_points
    ]
    sparse_index = SparseVectorIndex()
    sparse_index.fit(documents)
    return sparse_index


#the bm25 index is built from a corpus that only changes at ingest time, so building it on
#every sparse/hybrid query (scroll 10k docs + tokenize) was pure wasted latency. cache it
#and reuse across requests; call invalidate_sparse_index() after seeding new documents.
_sparse_index = None
_sparse_index_lock = threading.Lock()


def get_sparse_index(force_rebuild: bool = False):
    """Return the cached BM25 index, building it once on first use (thread-safe)."""
    global _sparse_index
    if _sparse_index is not None and not force_rebuild:
        return _sparse_index
    with _sparse_index_lock:
        if _sparse_index is None or force_rebuild:
            _sparse_index = _build_sparse_index()
    return _sparse_index


def invalidate_sparse_index() -> None:
    """Drop the cached BM25 index so the next search rebuilds it (call after re-seeding)."""
    global _sparse_index
    with _sparse_index_lock:
        _sparse_index = None


def sparse_search(query_text: str, top_k: int = 5) -> list[RetrievedChunk]:
    """Pure sparse search using BM25 (no dense embeddings, no fusion)."""
    return get_sparse_index().search(query_text, top_k=top_k)


#runs both dense and sparse search then merges the two ranked lists into one with rrf
def hybrid_search(
    query_embedding: list[float],
    query_text: str,
    top_k: int = 5,
    rrf_k: int = 60,
    sparse_top_k: int = 20,
) -> list[RetrievedChunk]:

    from app.services.sparse_vector_service import fuse_rrf
    dense_results = search(query_embedding, top_k=sparse_top_k)
    sparse_results = get_sparse_index().search(query_text, top_k=sparse_top_k)
    fused = fuse_rrf([dense_results, sparse_results], rrf_k=rrf_k)
    return fused[:top_k]
