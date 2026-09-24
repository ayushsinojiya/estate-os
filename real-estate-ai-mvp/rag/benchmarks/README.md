# Embedding benchmark

`dataset.py` is a checked-in, synthetic English canonical-property corpus and 40 hand-labeled queries. It covers English, Hindi, Marathi, Gujarati, separately labeled Romanized Hindi/Marathi/Gujarati, and mixed-language queries. Content preserves original property names. No translated document aliases are added. The sixteen curated properties have property-core, amenity, and connectivity sections, including near-name collisions, two configurations with identical BHK/area, independent properties, prices, possession, and distinct area types. Deterministic distractors bring the workload to 1,000 properties / 2,016 property-aware sections.

Run from the `rag` directory after installing project dependencies:

```powershell
.\.venv\Scripts\python.exe benchmarks\benchmark_embeddings.py --model e5
.\.venv\Scripts\python.exe benchmarks\benchmark_embeddings.py --model minilm
```

Both candidates run on CPU with four PyTorch threads (or fewer if the machine has fewer CPUs), normalized float32 vectors, and immutable model revisions. Each model's documented query/passage contract is used. Overlong inputs fail rather than silently dropping canonical facts. Model download/load timing is reported separately from first inference and warm single-query timing. Eighty warm query samples are measured (two passes of 40); documents are embedded in batches of 32. The measured environment and corpus/query SHA-256 are in each results JSON.

Accuracy uses exact cosine similarity over **all sections**, ranking properties by their best section score. Recall@1/3/5 and full-list MRR use the single labeled relevant property per query. Per-query ranks and top-five properties are retained for inspection. The metric is a property-level semantic retrieval diagnostic; it does not claim that vector similarity enforces exact BHK, price, or area constraints. No keyword retrieval, filters, reranker, ANN index, or query rewriting is included.

NumPy timing is an in-process exact **section** top-five workload, separate from the property-level quality calculation. It excludes SQL execution, network, embedding, and serialization, so it is **not** evidence of PostgreSQL latency.

To measure actual PostgreSQL + pgvector exact search, configure `RAG_BENCHMARK_DATABASE_URL` in the process environment with an existing pgvector-enabled test database. Do not place credentials in a checked-in file. The script creates only a transaction-local temporary table, inserts the measured vectors, analyzes the table, and records `EXPLAIN (ANALYZE, BUFFERS)` and 120 top-five query round trips. There is no vector index. After the model run, a database-only rerun can reuse the ignored local vectors:

```powershell
.\.venv\Scripts\python.exe benchmarks\benchmark_embeddings.py --model e5 --postgres-only
```

Model selection and limitations are in `REPORT.md`; raw measured evidence is in `e5_results.json` and `minilm_results.json`. This is a small diagnostic with synthetic distractors, not an independently held-out production dataset. Expand the labeled corpus with real, authorized examples before inferring market-wide language quality. Retain exact PostgreSQL search as the initial baseline; add ANN only after measuring a workload that requires it.

Official model documentation:

- [Multilingual E5 small](https://huggingface.co/intfloat/multilingual-e5-small) specifies `query: ` and `passage: ` roles, including non-English input, and a 512-token limit.
- [Multilingual MiniLM](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) specifies a 384-dimensional representation and its Sentence Transformers architecture's 128-token limit.
- [Microsoft E5 documentation](https://github.com/microsoft/unilm/blob/master/e5/README.md) lists the small multilingual model with 384 dimensions.
