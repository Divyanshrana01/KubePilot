from __future__ import annotations

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


#pulls every chunk out of qdrant and builds a fresh bm25 index over them for keyword search
#this is rebuilt on every call, fine for our doc count but wouldnt scale to a huge corpus
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

def sparse_search(query_text: str, top_k: int = 5) -> list[RetrievedChunk]:
    """Pure sparse search using BM25 (no dense embeddings, no fusion)."""
    sparse_index = _build_sparse_index()
    return sparse_index.search(query_text, top_k=top_k)


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
    sparse_index = _build_sparse_index()
    sparse_results = sparse_index.search(query_text, top_k=sparse_top_k)
    fused = fuse_rrf([dense_results, sparse_results], rrf_k=rrf_k)
    return fused[:top_k]
