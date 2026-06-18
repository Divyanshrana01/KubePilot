from __future__ import annotations

import os

from datasets import Dataset
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI
from ragas import evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import llm_factory
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)


from app.config import settings


#these are the 4 ragas metrics we evaluate every answer on:
# - faithfulness: did the answer stick to what the retrieved chunks said?
# - context_precision: did we retrieve the right chunks?
# - context_recall: did we retrieve all the relevant chunks?
# - answer_relevancy: did the answer actually answer the question?
METRICS = [
    faithfulness,
    context_precision,
    context_recall,
    answer_relevancy,
]


#creates a ragas-compatible llm wrapper using our app's grader model
def _get_ragas_llm():
    """Create a Ragas-compatible LLM using app settings."""
    os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    client = OpenAI(api_key=settings.openai_api_key)
    return llm_factory(settings.llm_model_grader, client=client)

#creates a ragas-compatible embedding wrapper using our app's embedding model
def _get_ragas_embeddings():
    """Create Ragas-compatible embeddings using app settings."""
    lc_emb = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
    )
    return LangchainEmbeddingsWrapper(lc_emb)

#packs the eval rows into the format that ragas expects as input
def build_dataset(rows: list[dict]) -> Dataset:
    return Dataset.from_dict(
        {
            "user_input": [r["question"] for r in rows],
            "response": [r["answer"] for r in rows],
            "retrieved_contexts": [r["contexts"] for r in rows],
            "reference": [r["ground_truth"] for r in rows],
        }
    )

#this fn takes the list of eval rows and runs ragas on them.
#returns one dict per row with all 4 metric scores filled in.
def run(rows: list[dict]) -> list[dict]:
    if not rows:
        return []

    ds = build_dataset(rows)
    result = evaluate(
        ds,
        metrics=METRICS,
        llm=_get_ragas_llm(),
        embeddings=_get_ragas_embeddings(),
        show_progress=False,
    )
    return result.to_pandas().to_dict(orient="records")



