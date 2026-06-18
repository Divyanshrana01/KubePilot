from openai import OpenAI

from app.config import settings
from app.services.query_cache_service import query_cache


#shared openai client used for all embedding calls
openai_client = OpenAI(api_key=settings.openai_api_key)

#this fn takes a list of text strings and returns a list of embeddings (float vectors).
#it checks the cache first for each text, only calls openai for the ones that aren't cached yet.
#this saves money and speeds things up a lot when the same texts are embedded repeatedly.
def embed_texts(texts: list[str], model: str | None = None) -> list[list[float]]:
    if not texts:
        return []
    if model is None:
        model = settings.embedding_model

    #pre-fill results with None, we'll fill in cache hits and api results below
    results: list[list[float] | None] = [None] * len(texts)
    miss_indices: list[int] = []
    miss_texts: list[str] = []

    #go through each text and check if we already have its embedding cached
    for i, text in enumerate(texts):
        cached = query_cache.get_embedding(text)
        if cached is not None:
            results[i] = cached
        else:
            #track which texts we need to send to openai
            miss_indices.append(i)
            miss_texts.append(text)

    #only call openai if there are texts we didnt find in the cache
    if miss_texts:
        response = openai_client.embeddings.create(input=miss_texts, model=model)
        for idx_in_misses, item in enumerate(response.data):
            original_idx = miss_indices[idx_in_misses]
            vector = item.embedding
            results[original_idx] = vector
            #save the new embedding to cache so next time we wont need to call openai
            query_cache.set_embedding(miss_texts[idx_in_misses], vector)

    return [r for r in results if r is not None]

