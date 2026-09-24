# V1 measured embedding decision

Select **`intfloat/multilingual-e5-small`**, immutable revision **`614241f622f53c4eeff9890bdc4f31cfecc418b3`**, 384 dimensions, normalized float32 vectors, document prefix `passage: ` and query prefix `query: `. This decision follows successful inference and retrieval runs of both candidates; no model was selected from a model-card claim alone. Keep the provider configurable and atomically rebuild all live embeddings when its identity changes.

## Actual results

The checked-in JSON files contain the measured environment, timestamp, dataset hash, every query/rank/top-five result, and timings. Both runs used 1,000 synthetic properties, 2,016 property-aware sections, and 40 labeled queries. Each language group has five queries. Property ranking takes the best exact cosine score among its sections; it does not apply exact metadata filters.

| Measure | Multilingual E5 small | Multilingual MiniLM L12 v2 |
|---|---:|---:|
| Property recall@1 | 87.5% | 52.5% |
| Property recall@3 | 97.5% | 60.0% |
| Property recall@5 | 97.5% | 62.5% |
| Full-list MRR | 0.9212 | 0.5760 |
| Warm query embedding median | 24.92 ms | 27.44 ms |
| Warm query embedding p95 | 42.28 ms | 36.79 ms |
| First query after model load | 143.78 ms | 161.69 ms |
| Model load, including download when uncached | 105.41 s | 116.95 s |
| Embed all 2,016 sections | 28.39 s | 29.44 s |
| Dimensions | 384 | 384 |
| Max sequence length | 512 tokens | 128 tokens |
| External inference cost | $0 | $0 |

E5 offers substantially better measured retrieval accuracy at similar local CPU query latency. Its lower accuracy on some native-script cases matters more than the small latency differences. The `$0` figure means no paid inference API was called; it excludes hardware, electricity, network, and first-download costs.

| Query group | E5 recall@1 / @5 | MiniLM recall@1 / @5 |
|---|---:|---:|
| English | 100% / 100% | 60% / 60% |
| Hindi | 80% / 80% | 40% / 40% |
| Marathi | 80% / 100% | 60% / 100% |
| Gujarati | 60% / 100% | 20% / 40% |
| Romanized Hindi | 100% / 100% | 40% / 60% |
| Romanized Marathi | 100% / 100% | 40% / 40% |
| Romanized Gujarati | 80% / 100% | 60% / 60% |
| Mixed language | 100% / 100% | 100% / 100% |

## Limits and observed failure cases

This is a small, hand-authored diagnostic. Sixteen curated properties carry the labels; 984 generated distractor properties test expected scale. The same intents appear across several languages. These are not independent held-out examples and the percentages do not estimate production-wide accuracy. The English canonical corpus tests multilingual query-to-English retrieval, not every possible source language. No customer documents were sent to any external service.

E5 missed the native Hindi Andheri West 1 BHK query (`hi-4`) at rank 63. Gujarati and Romanized Gujarati South Bopal queries put the wrong Shivalik Sky configuration first even though the requested price distinguishes them (`gu-1`, `romanized_gu-1`, correct rank 2). Gujarati Paldi (`gu-3`) ranked second; Marathi Wakad/780-sqft (`mr-4`) ranked third. These are visible in the raw per-query evidence. Semantic similarity alone is not a substitute for typed price/BHK/area/location filters, keyword matching, or the voice agent's retrieval work. There is not enough evidence here to justify automatic translated aliases for every property; preserve exact original names and expand labeled examples before choosing a targeted improvement.

## Exact search at V1 scale

The local **NumPy** exact top-five section search over all 2,016 vectors measured median **0.184 ms**, p95 **0.258 ms** for E5 and median **0.136 ms**, p95 **0.222 ms** for MiniLM (120 samples each). This excludes database work, serialization, and embedding. Equal dimensions explain why model choice is not the major vector scan cost here; variation is local timing noise.

**PostgreSQL + pgvector was measured in a subsequent database-only run on 2026-09-23.** PostgreSQL 16.15 with pgvector 0.8.6 ran in local Docker, using the saved actual vectors, a temporary table, exact sequential scan, and `EXPLAIN (ANALYZE, BUFFERS)`. At 2,016 rows, 120 warm top-five section queries including local client round trips measured E5 median **2.42 ms**, p95 **3.91 ms**; MiniLM median **2.42 ms**, p95 **3.89 ms**. These exclude query embedding, voice/STT/TTS, ranking and the CRM. Raw plans and timings are in the candidate result JSON files. NumPy timings above remain a separate measurement.

V1 keeps exact search and adds no HNSW/IVFFlat index. The measured database baseline supports exact search first at this size. This is not a concurrency/load-test or production latency guarantee; no ANN comparison or larger-scale capacity claim is made.

## Reproduction and deployment configuration

Runs used Windows 11, Intel Core i5-1135G7 (4 physical / 8 logical cores), Python 3.12.10, CPU-only inference with four PyTorch threads, sentence-transformers 5.7.0, torch 2.14.0, transformers 5.17.0, and numpy 2.5.3. E5 started at `2026-09-22T19:46:43Z`; MiniLM started at `2026-09-23T00:44:39Z`. Load timing is measured elapsed wall time, not a guaranteed deployment startup budget; internet and cache state affect it. Warm single-query latency has 80 samples per model, two passes over the 40 queries.

The corpus plus queries SHA-256 is `e49f81ee3ae8d892016d2c8037cff2d1ddeb96253fe5139a18369f3ba434e59d` for both runs. The alternative MiniLM revision is `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`.

```python
provider = SentenceTransformerProvider(
    model_name="intfloat/multilingual-e5-small",
    revision="614241f622f53c4eeff9890bdc4f31cfecc418b3",
)
document_vectors = provider.embed(canonical_sections)
query_vectors = provider.embed_queries(runtime_queries)
```

Load the provider once per worker/runtime, not once per query. Package/cache the pinned public model before offline operation; `local_files_only=True` fails clearly when weights are missing. Keep the recorded provider identity alongside each embedding set. Model load, inference, overlong section, and invalid vector errors must fail staging; there is no hash-vector or random-vector fallback. Provider contract tests passed: **7 tests** via `.venv\Scripts\python.exe -m pytest tests\test_embeddings.py -q`.

Official references used to configure the experiment: [E5 model card](https://huggingface.co/intfloat/multilingual-e5-small), [Microsoft E5 documentation](https://github.com/microsoft/unilm/blob/master/e5/README.md), and [MiniLM model card](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2). Performance values above come from this repository's runs, not from those model cards.
