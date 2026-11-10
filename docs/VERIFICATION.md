# Verification record — 2026-11-10

- `python -m pytest -q tests`: **17 passed** (local environment, Python 3.13.5).
- `python -m compileall -q app`: **passed**.
- HTTP smoke check: **GET /healthz = 200, POST /v1/documents = 201, POST /v1/ask = 200**, using actual loopback Uvicorn server.
- Benchmark: `python benchmarks/run.py` with 30 fixed synthetic queries/documents; observed results retained in `benchmarks/results.json` and `benchmarks/summary.csv`.
- Docker image/Compose deployment: **not run (Docker unavailable in execution environment)**.
- External OpenAI embedding/chat: **not run (credentials unavailable)**.
- Cloud deployment and load tests: **not performed**.

## Benchmark summary

| Mode | Recall@1 | Recall@3 | MRR@3 | Median retrieval | p95 retrieval |
|---|---:|---:|---:|---:|---:|
| lexical | 93.3% | 96.7% | 0.944 | 5.48 ms | 9.91 ms |
| vector | 60.0% | 80.0% | 0.672 | 5.69 ms | 10.26 ms |
| hybrid | 86.7% | 93.3% | 0.889 | 5.42 ms | 9.47 ms |

Latency is local single-process retrieval only; NOT production or HTTP latency. Local vector mode uses feature hashing, not a neural embedding. No answer faithfulness benchmark was conducted.
