# Enterprise RAG Knowledge Intelligence Platform
## Production-Grade Portfolio Deployment & Verification Playbook

**Project baseline:** existing `enterprise-rag-platform` ZIP, verified 2026-11-10.  
**Status:** local tests and synthetic benchmarks passed; no cloud service or Docker deployment has yet been verified.  
**Recommended deployment target:** AWS ECS/Fargate + RDS PostgreSQL/pgvector + S3 + ALB/ACM + CloudFront + CloudWatch + GitHub Actions OIDC.  
**Cost warning:** RDS, ECS, ALB, NAT/networking, CloudFront, and model calls can incur ongoing charges. Set AWS Budgets alerts before provisioning; stop/delete resources when not needed.

## Acceptance gates

- **Gate A — Reproduce baseline:** clean clone, `17` existing tests pass (or updated suite passes), `/healthz`, ingest, ask, and audit functions work in containers. Secure demo identities; no default secrets.
- **Gate B — Real RAG:** neural embeddings configured, corpus re-indexed, cited answers generated, citations verified. End-to-end model integration tests executed with credentialed staging environment.
- **Gate C — Storage migration:** operational PostgreSQL/pgvector adapter (new code), schema migrations, S3 document storage, tenant filtering inside every query, backup/restore test.
- **Gate D — Security:** OIDC login (new code), role/group enforcement, rate and spending limits, prompt-injection and document-access adversarial tests. Never publicly expose admin API keys or docs with write access to anonymous users.
- **Gate E — Public cloud:** deploy immutable image via ECR to ECS, TLS using ACM and ALB, static UI on CloudFront/S3 (or protected Nginx), healthy service and rollback procedure.
- **Gate F — Measurable result:** 100–500 human-labeled public/synthetic questions; Recall@1/3/5, MRR/nDCG, citation correctness, unsupported-answer rate, p50/p95 E2E latency, errors, throughput, spend; actual runs attached with git commit and timestamps.
- **Gate G — Portfolio:** public GitHub repo without secrets, architecture, reproducible scripts, 2–3 min narrated demo, sanitized benchmark artifacts, link to safe read-only public demo.

## Step 1 — Prepare workstation and safe source control

1. Install Docker Desktop with Compose v2, Git, Python 3.12+, VS Code, and an AWS CLI for deployment work.
2. Download and extract the previously supplied ZIP. The archive contains a root `enterprise-rag-platform/` folder. In that folder run:

   ```bash
   python --version
   docker --version
   docker compose version
   git init
   git add .
   git commit -m "Baseline enterprise RAG application"
   ```

3. Create a **new empty GitHub repository**, connect it via `git remote add origin ...`, and push. Do not commit `.env`, API keys, uploaded files or local databases; inspect `git status` and `.gitignore` first.
4. Branch for upgrades (`git switch -c feature/neural-rag`). Keep `main` deployable.

## Step 2 — Establish the baseline locally

1. Generate unique keys: `python -c "import secrets; print(secrets.token_urlsafe(32))"` (run separately for each key).
2. On Linux/macOS: `cp .env.example .env`. On PowerShell: `Copy-Item .env.example .env`.
3. Edit `.env` replacing **all** `replace-...` example keys. Keep `EMBEDDING_PROVIDER=local` and `ANSWER_PROVIDER=extractive` for the first smoke test.
4. Start containers:

   ```bash
   docker compose up --build -d
   docker compose ps
   docker compose logs --tail=100 api
   curl http://localhost:8000/healthz
   ```

5. Visit `http://localhost:8080`; enter an admin key, upload `sample_data/demo_policy.md` and ask "What is the RTO?" Confirm cited sources and the correct document scope.
6. Run regression suite:

   ```bash
   python -m venv .venv
   # Linux/macOS: source .venv/bin/activate
   # PowerShell: .venv\Scripts\Activate.ps1
   python -m pip install -r requirements-dev.txt
   python -m pytest -q tests
   python benchmarks/run.py
   ```

7. Keep the newly generated benchmark results and test logs. The baseline `17 passed` and 30 synthetic questions are **previous local results**, not independently verified cloud performance.
8. **Do not use** `docker compose down -v` unless intentionally deleting all contents of the named volume.

## Step 3 — Activate actual LLM-driven RAG

1. Acquire OpenAI API credentials, enable usage limits and create a restricted key; keep it only in `.env` for local development and AWS Secrets Manager for cloud deployment.
2. Use a **new disposable indexing volume** for model migration; vector indexes produced by the default hashed local embedding **cannot be compared** with OpenAI neural embeddings.
3. Update `.env`:

   ```dotenv
   EMBEDDING_PROVIDER=openai
   EMBEDDING_MODEL=text-embedding-3-small
   ANSWER_PROVIDER=openai
   CHAT_MODEL=gpt-4.1-mini
   OPENAI_API_KEY=replace_me_locally_only
   ```

4. The current code requests 256-dimensional neural embeddings. If changing to another embedding model, confirm its `dimensions` support and update the schema and vector handling appropriately.
5. Rebuild and re-ingest a *disposable* corpus. To reset the demo volume **only if it contains no valuable data**, run `docker compose down -v` then `docker compose up --build -d`; otherwise implement a migration/reindex job instead.
6. Test a known answer and an unanswerable question; verify citations point to retrieved chunks, model refusal/abstention on missing evidence, handling of model errors and API spend. **Do not claim model accuracy until evaluated.**
7. Add integration tests using a mocked API for CI and a real credentialed staging run for periodic validation. Keep external-key tests out of pull-request forks.

## Step 4 — Refactor application boundaries

Current `app/core.py` uses SQLite directly. The following are **new engineering tasks**, not existing switches:

- `app/repositories/`: interface for documents, chunks, users, ACLs, audit events.
- `app/retrieval/`: independent lexical, vector, hybrid, rerank strategies.
- `app/ingestion/`: parser, chunker, embedder, re-index jobs.
- `app/security/`: OIDC middleware, tenant/group access policy.
- `app/answering/`: answer model, citation verification, abstention rules.
- `app/observability/`: structured logs, metric labels, traces.
- `migrations/`: Alembic schemas and revision scripts.

Preserve FastAPI `/v1/ask` and `/v1/documents` response contracts where possible; add contract tests prior to refactoring. Every document and chunk must carry trusted tenant and authorization metadata; filter candidates *inside storage/retrieval queries*, not just after getting global nearest neighbors.

## Step 5 — PostgreSQL/pgvector and S3 migration

1. Prototype the schema in a local PostgreSQL container, not production RDS first.
2. Install SQLAlchemy, Alembic, psycopg and a pgvector driver, pin versions and add migration CI.
3. Suggested tables: `tenants`, `identities`, `groups`, `documents`, `document_acl`, `chunks` (with `embedding vector(256)` for this model), `ingest_jobs`, `audit_events`. Store document payload in private S3, and metadata, content excerpts and vector embeddings in RDS.
4. Set up PostgreSQL `CREATE EXTENSION IF NOT EXISTS vector;` in a supported instance/version. Index vector similarity using HNSW after baseline EXPLAIN/ANALYZE measurements. Retain lexical full-text search and implement reciprocal rank fusion.
5. Ensure each read/delete/indexing call uses server-derived tenant/group constraints. Create test tenants A/B and groups Engineering/Finance; verify no cross-tenant or unauthorized result is possible even when the top global neighbor belongs to another tenant.
6. Backfill only synthetic data, run embedding consistency checks, and validate backup/restore, migration rollback, ingestion retry and idempotency.
7. In RDS select an appropriate PostgreSQL version with the pgvector extension supported in the chosen region; configure private subnet, security groups, encryption, automated backups, storage monitoring and database credentials via Secrets Manager.
8. Create an encrypted, private S3 bucket with public access blocked, versioning as needed, lifecycle and expiration policies. Use task IAM roles for S3 access.

**Important:** current code does **not** have a PostgreSQL adapter, S3 adapter, OCR, queue, or OIDC provider. These must be implemented, tested, and deployed before claiming those features.

## Step 6 — Harden identity, security, and reliability

1. Replace `.env`-supplied static user API keys with OIDC (e.g., Cognito/enterprise identity provider), with JWT signature, issuer, audience and expiration validation. Implement group membership derived from trusted identity or server-side directory mapping.
2. Admin document upload is private/SSO only; public portfolio demo is read-only and rate-limited, with a fixed curated synthetic dataset and no unrestricted arbitrary document upload.
3. Apply max upload size, PDF parsing isolation, antivirus/malware scan, file magic validation, OCR worker isolation if needed, safe content handling and request timeouts.
4. Create robust LLM prompt-injection defenses: treat retrieved document text as untrusted, do not allow retrieved content to call privileged tools, validate generated citation IDs against retrieved chunks, and set refusal rules for absent evidence.
5. Add per-user, per-tenant and per-IP rate limits, token/cost budgets, usage alerts and automated circuit breakers. Redact query bodies and PII from logs; the baseline demo currently logs the beginning of queries and should be changed before processing sensitive content.
6. Scan dependencies and Docker image, run containers as non-root, pin base images by digest, generate SBOM, set resource limits and egress policies, and document incident/rollback procedure.
7. Enforce TLS, CORS, security headers, network isolation, encryption at rest, restore drills, retention policy and least-privilege IAM.

## Step 7 — Cloud provisioning with AWS

1. Create a separate AWS project account or sandbox. Turn on AWS Budgets with alert thresholds and tag all resources (`Project=EnterpriseRAG`, `Environment=portfolio`). Get current pricing for region and capacity *before* deploying; no fixed monthly cost is promised.
2. Choose one AWS region; configure a VPC across at least 2 availability zones, public subnets for ALB, private subnets for ECS tasks/RDS, and security groups: internet→ALB 443; ALB→ECS app port; ECS→RDS 5432. Minimize expensive NAT deployment where practical and review VPC endpoint options.
3. Set up Amazon ECR repository and private IAM task execution/task roles. Publish an image built from the application Dockerfile; verify it using a local `docker build` and image vulnerability scan first.
4. Create private RDS PostgreSQL, enable pgvector, run Alembic migrations via a controlled migration job. Provision private S3 bucket and Secrets Manager secrets.
5. Create an ECS Fargate task definition with environment references to Secrets Manager, explicit CPU/memory, a health check (`/healthz`), and CloudWatch logging. Deploy an ECS service behind a target group and Application Load Balancer.
6. Set an ACM-issued TLS certificate and HTTPS ALB listener for `api.yourdomain.example`. Put the web frontend behind CloudFront (static S3 origin is recommended after adapting the frontend to call the public API origin); keep private APIs inaccessible without authorization.
7. Configure DNS records and verify browser TLS, CORS, auth, health endpoints, database connectivity, S3 access and end-to-end RAG. **Port 8000 should never be internet-open on an ECS task.**
8. Configure CloudWatch alarms for 5xx, target health, CPU/memory, RDS connections and storage, unusual API call volume and costs. Test scaling, rollback and backup restore before portfolio launch.
9. Once hosted, record exact architecture, commit SHA, deployment date, region (without exposing secrets), uptime window and observed operating cost.

## Step 8 — CI/CD with GitHub Actions

Existing `.github/workflows/ci.yml` runs tests, benchmarks and byte-compilation on pushes/PRs; extend it:

1. PR checks: lint/format, type-check, unit/integration/security tests, dependency audit, container build, artifact collection, no credentials.
2. Merge-to-main: re-run gate, create tagged immutable image, scan it, push to ECR, assume a **scoped** AWS IAM deployment role via GitHub OIDC (no static AWS access keys), update ECS task and wait for stable deployment.
3. Add protected GitHub environment approval for `production`; only trusted branch/ref may assume AWS role.
4. Run post-deploy smoke tests of health, authorized synthetic query, forbidden cross-tenant query and source citation; stop promotion or roll back if any fail.
5. Persist test reports, benchmark outputs, deployment SHA, and signed artifact metadata.

GitHub documentation: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws

## Step 9 — Evaluation and load-testing methodology

1. Create 100–500 labeled QA cases across engineering, finance, operations, HR and general policy. Use synthetic/public content; keep an immutable evaluation set held out from tuning.
2. For each question store expected relevant document/chunk IDs, expected answer facts, expected abstain flag, user/tenant/groups and difficulty category. Include adversarial cross-tenant questions and prompt-injection documents.
3. Compare **lexical**, **neural vector**, **hybrid**, and (when implemented) **hybrid+reranking** at identical top-k and candidate access scope. Record Recall@1/3/5, MRR@3, nDCG@5 and zero-access-leak count.
4. Assess generated answers separately: supported-claim precision, citation correctness, abstention accuracy, unsupported-answer rate, reviewer consistency, and (if available) answer faithfulness using both human review and a carefully calibrated judge model.
5. Run controlled HTTP load tests using Locust or k6 with 1, 5, 10, 25 concurrent virtual users (adjust safely to budget and service capacity); record p50/p95/p99 end-to-end latency, throughput, error rate, CPU/memory, OpenAI tokens/estimated cost per 100 questions. Distinguish warm and cold runs.
6. Use repeated runs, fixed code revision and corpus, same region, same model version where possible. Capture timestamp, parameter settings, raw CSV/JSON and summary charts.
7. **Publish measured results, including regressions**. Current local synthetic baseline (retrieval-only) is lexical Recall@3 96.7%, local hash vector 80.0%, hybrid 93.3%; those are *not* neural-embedding or public-cloud results.

Suggested initial release targets (goals, **not achieved measurements**): ACL leaks `0`, recall@3 `>= 0.90` on your defined held-out corpus, citation correctness `>= 0.95`, HTTP 5xx rate `< 1%`, p95 end-to-end `< 5 s` at 5 virtual users, budget within your cap. Revise targets once workload and quality requirements are understood.

## Step 10 — Portfolio publishing and interviewing

1. Create a polished GitHub README explaining problem, architecture, setup, security model, evaluation methods, design tradeoffs, observed results, cost and limitations.
2. Add demo screenshots of document upload, answers with citations, evaluation dashboard, observability and an intentional unauthorized-access failure.
3. Publish a 2–3-minute walkthrough: value proposition → upload synthetic documents (private admin demo) → ask questions → inspect citations → show denied access → benchmark chart → deployment and monitoring.
4. Link `https://demo.yourdomain.example` (read-only) and GitHub repository on resume/LinkedIn, but do not publish a real URL until it exists.
5. Keep a short architecture decision record for FTS5 vs PostgreSQL, BM25 vs vectors, fusion strategy, choice of model, isolation boundary and rollbacks.
6. Accurate resume bullet once completed: "Designed, deployed and evaluated a multi-tenant RAG knowledge platform using FastAPI, PostgreSQL/pgvector, AWS ECS, S3, OIDC, neural embeddings, hybrid search and citation-grounded LLM responses; implemented automated CI/CD, monitoring, access-control tests and reproducible retrieval/load benchmarks." Add **actual numeric metrics only after rerunning production evaluations**.

## Rollout order

**Milestone 1 (immediate):** baseline local, 17 tests, synthetic-only demo, no secrets.  
**Milestone 2:** OpenAI neural embeddings and answers, integration tests, baseline comparisons.  
**Milestone 3:** service modularization, PostgreSQL/pgvector, S3, data migrations.  
**Milestone 4:** SSO, ACL/security tests, safe read-only demo configuration.  
**Milestone 5:** ECS/RDS/CloudFront deployment, DNS/TLS, logs/alerts, CI/CD.  
**Milestone 6:** held-out evaluation, load tests, cost reports, video, resume and public GitHub.

## References

- AWS RDS PostgreSQL extension documentation: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Extensions.html
- AWS PostgreSQL extension versions: https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html
- GitHub Actions AWS OIDC: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws
- GitHub AWS credential action guidance: https://github.com/aws-actions/configure-aws-credentials

**Explicit limitations:** This document is a production implementation *plan and guide*, not evidence that listed upgrades or cloud resources have been created. The existing ZIP remains a local reference app until these tasks are implemented and verified.
