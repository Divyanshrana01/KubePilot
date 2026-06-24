# Evaluation Results

RAGAS metrics measured against the 31-question golden K8s incident set (`eval/seed_questions.yaml`, excluding sql/hybrid-intent questions, which the service-mode harness doesn't score). Each phase enables one more retrieval/generation technique on top of the previous row; raw run outputs are in `eval/results/*.json`.

| Phase | Faithfulness | Context Precision | Context Recall | Answer Relevancy |
|---|---|---|---|---|
| Naive (dense-only retrieval) | 0.775 | 0.370 | 0.473 | 0.701 |
| + Hybrid search + rerank | 0.802 | 0.371 | 0.470 | 0.702 |
| + HyDE + CRAG + Self-RAG (full pipeline) | 0.867 | 0.465 | 0.492 | 0.766 |

**Naive** row is averaged across 3 runs (`20260618T185457Z`, `20260618T194021Z`, `20260618T194158Z`) to smooth out LLM-judge variance. **Hybrid search + rerank** is `20260620T162006Z_hybrid+rerank.json`. **Full pipeline** is `20260624T123337Z_all.json`; its faithfulness is the mean over the 25/31 rows the RAGAS judge could score (6 returned NaN — judge errors, not failed retrievals).

## Targeted CRAG check

A separate run filtered to the 8 questions specifically designed to exercise the CRAG fallback path (`20260623T010151Z_hybrid+rerank+crag.json`, `filter: crag`) scored faithfulness 0.975 / context precision 0.392 / context recall 0.458 / answer relevancy 0.800. Not included in the table above since it's a different (smaller) question subset, not a like-for-like comparison.

## Caveats

- Context precision and recall stay low (0.37-0.49) across every phase — retrieval over the K8s corpus (which is deliberately 95% noise PDFs) is the current bottleneck, not generation.
- Faithfulness gains are real but the judge occasionally fails to score a row (NaN); those rows are excluded from the mean rather than counted as 0.
- Numbers come from `mode: service` runs against the live FastAPI service, not offline replay — re-running will reproduce similar but not identical scores due to LLM-judge nondeterminism.

Reproduce with:

```bash
python eval/run_ragas.py --profile naive
python eval/run_ragas.py --profile hybrid+rerank
python eval/run_ragas.py --profile all
```
