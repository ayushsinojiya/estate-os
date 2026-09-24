"""Reproducible local CPU evaluation; run from rag/.

python benchmarks/benchmark_embeddings.py --model e5
python benchmarks/benchmark_embeddings.py --model minilm
Set RAG_BENCHMARK_DATABASE_URL to a disposable pgvector-enabled database for
actual database timing (only a transaction-local temporary table is created).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dataset import corpus, queries
from rag_ingestion.embeddings import SentenceTransformerProvider

CANDIDATES = {
    "e5": ("intfloat/multilingual-e5-small", "614241f622f53c4eeff9890bdc4f31cfecc418b3"),
    "minilm": ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"),
}


def percentiles(values):
    import numpy as np
    return {"median_ms": float(statistics.median(values)), "p95_ms": float(np.percentile(values, 95)), "samples": len(values)}


def metrics(rows):
    return {
        "queries": len(rows),
        "recall_at_1": sum(r["rank"] <= 1 for r in rows) / len(rows),
        "recall_at_3": sum(r["rank"] <= 3 for r in rows) / len(rows),
        "recall_at_5": sum(r["rank"] <= 5 for r in rows) / len(rows),
        "mrr": sum(1 / r["rank"] for r in rows) / len(rows),
    }


def postgres_timing(vectors, query_vectors):
    """Exact top-5 SECTION search, including local client round trip.

    This is a separate timing workload from property-level quality scoring.
    Uses all section vectors, no ANN index, a transaction-local temp table.
    """
    dsn = os.getenv("RAG_BENCHMARK_DATABASE_URL")
    if not dsn:
        return {"status": "not_run", "reason": "RAG_BENCHMARK_DATABASE_URL not configured; NumPy timing is not a PostgreSQL benchmark"}
    import psycopg
    def literal(vector):
        return "[" + ",".join(str(float(x)) for x in vector) + "]"
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            extension = cur.fetchone()
            if not extension:
                raise RuntimeError("Benchmark database lacks pgvector; install extension explicitly")
            cur.execute(f"CREATE TEMP TABLE embedding_benchmark (id integer, embedding vector({vectors.shape[1]})) ON COMMIT DROP")
            with cur.copy("COPY embedding_benchmark (id, embedding) FROM STDIN") as copy:
                for index, vector in enumerate(vectors):
                    copy.write_row((index, literal(vector)))
            cur.execute("ANALYZE embedding_benchmark")
            sample = literal(query_vectors[0])
            cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT id FROM embedding_benchmark ORDER BY embedding <=> %s::vector LIMIT 5", (sample,))
            plan = cur.fetchone()[0]
            times = []
            for _ in range(3):
                for vector in query_vectors:
                    value = literal(vector)
                    started = time.perf_counter()
                    cur.execute("SELECT id FROM embedding_benchmark ORDER BY embedding <=> %s::vector LIMIT 5", (value,))
                    cur.fetchall()
                    times.append((time.perf_counter() - started) * 1000)
            cur.execute("SELECT version()")
            return {"status": "completed", "pgvector_version": extension[0], "postgres_version": cur.fetchone()[0], "rows": len(vectors), "index": "none (exact sequential scan)", "top_k": 5, "round_trip": percentiles(times), "explain_analyze": plan}


def run(key, property_count):
    import numpy as np
    import torch
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    torch.manual_seed(0)
    documents, labels = corpus(property_count), queries()
    result = {
        "candidate": key, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_name": CANDIDATES[key][0], "revision": CANDIDATES[key][1],
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "processor": platform.processor(), "logical_cpus": os.cpu_count(), "torch_threads": torch.get_num_threads(), "device": "cpu", "dependencies": {p: importlib.metadata.version(p) for p in ["sentence-transformers", "torch", "transformers", "numpy"]}},
        "dataset": {"properties": property_count, "sections": len(documents), "queries": len(labels), "synthetic": True, "sha256": hashlib.sha256(json.dumps([documents, labels], ensure_ascii=False, sort_keys=True).encode()).hexdigest()},
        "cost": {"external_inference_usd": 0, "note": "Local CPU inference; hardware, electricity and one-time public model download are not priced"},
    }
    started = time.perf_counter()
    print(f"Loading {key} pinned model on CPU...", flush=True)
    provider = SentenceTransformerProvider(*CANDIDATES[key])
    result["model_load_seconds_including_download_if_uncached"] = time.perf_counter() - started
    result["model_id"] = provider.model_id
    result["dimension"] = provider.dimension
    started = time.perf_counter()
    provider.embed_queries([labels[0]["text"]])
    result["cold_first_query_ms_after_load"] = (time.perf_counter() - started) * 1000
    print(f"Embedding {len(documents)} canonical sections...", flush=True)
    started = time.perf_counter()
    vectors = np.asarray(provider.embed([d["content"] for d in documents]), dtype=np.float32)
    result["corpus_embedding_seconds"] = time.perf_counter() - started
    query_vectors, latency = [], []
    for repeat in range(2):
        for item in labels:
            started = time.perf_counter()
            vector = provider.embed_queries([item["text"]])[0]
            latency.append((time.perf_counter() - started) * 1000)
            if repeat == 0:
                query_vectors.append(vector)
    result["warm_single_query_embedding"] = percentiles(latency)
    query_vectors = np.asarray(query_vectors, dtype=np.float32)
    rows = []
    for item, vector in zip(labels, query_vectors):
        # Exact cosine on unit vectors; maximum section score per property.
        order = np.argsort(-(vectors @ vector), kind="stable")
        ranked = list(dict.fromkeys(documents[int(i)]["entity_id"] for i in order))
        rank = min(ranked.index(target) + 1 for target in item["relevant"])
        rows.append({**item, "rank": rank, "top_5": ranked[:5]})
    result["quality"] = metrics(rows)
    result["by_language"] = {language: metrics([r for r in rows if r["language"] == language]) for language in sorted(set(r["language"] for r in rows))}
    result["per_query"] = rows
    times = []
    for _ in range(3):
        for vector in query_vectors:
            started = time.perf_counter()
            scores = vectors @ vector
            top = np.argpartition(-scores, 5)[:5]
            np.argsort(-scores[top])
            times.append((time.perf_counter() - started) * 1000)
    result["numpy_exact_section_top5"] = {**percentiles(times), "rows": len(vectors), "note": "In-process dense cosine + top-5, excludes DB/serialization/embedding"}
    print("Measuring optional PostgreSQL exact search...", flush=True)
    try:
        result["postgres_exact"] = postgres_timing(vectors, query_vectors)
    except Exception as exc:
        result["postgres_exact"] = {"status": "failed", "error_type": type(exc).__name__, "reason": str(exc)}
    # Retain actual vectors for a later DB-only run without repeating inference.
    np.savez_compressed(Path(__file__).parent / f"{key}_vectors.npz", vectors=vectors, queries=query_vectors)
    result["status"] = "completed"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=CANDIDATES, required=True)
    parser.add_argument("--properties", type=int, default=1000)
    parser.add_argument("--postgres-only", action="store_true")
    args = parser.parse_args()
    output = Path(__file__).parent / f"{args.model}_results.json"
    if args.postgres_only:
        import numpy as np
        saved = np.load(Path(__file__).parent / f"{args.model}_vectors.npz")
        data = json.loads(output.read_text(encoding="utf-8"))
        data["postgres_exact"] = postgres_timing(saved["vectors"], saved["queries"])
    else:
        try:
            data = run(args.model, args.properties)
        except Exception as exc:
            data = {"candidate": args.model, "status": "failed", "error_type": type(exc).__name__, "reason": str(exc), "timestamp_utc": datetime.now(timezone.utc).isoformat()}
            output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            raise
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: data[key] for key in ("status", "quality", "warm_single_query_embedding", "postgres_exact") if key in data}, indent=2), flush=True)
