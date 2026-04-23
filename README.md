# Roundup

Roundup is a backend-first, self-hosted news intelligence pipeline. It ingests articles from Miniflux, deduplicates them, clusters related coverage into strict story objects, and serves those objects through typed APIs.

## What v1 does
- Pulls articles from Miniflux only.
- Normalizes and stores raw + derived article features.
- Deduplicates using a stable hash.
- Clusters related articles with deterministic heuristics (no LLM clustering).
- Enriches strict cluster fields with deterministic fallback text.
- Exposes validated clusters from API endpoints.
- Exposes debug and Prometheus metrics endpoints.

## Stack
- FastAPI
- PostgreSQL
- SQLAlchemy + Alembic
- Docker Compose

## Repository structure
- `app/main.py` - FastAPI entrypoint and `/metrics`.
- `app/api/routes/` - health, public API, and debug endpoints.
- `app/services/` - ingestion, normalization, clustering, enrichment, validation, metrics, pipeline.
- `app/db/models.py` - SQLAlchemy models.
- `alembic/` - DB migration setup.
- `scripts/run_pipeline_once.py` - manual pipeline run utility.
- `docs/architecture.md` - architecture rationale.

## Quick start
1. Copy env template.
   ```bash
   cp .env.example .env
   ```
2. Update `.env` with your Miniflux URL and API token.
3. Start services.
   ```bash
   docker compose up --build
   ```
4. Verify health.
   ```bash
   curl http://localhost:8000/health
   ```

## Required endpoints
- `GET /health`
- `GET /metrics`
- `GET /api/articles`
- `GET /api/clusters`
- `GET /api/clusters/{cluster_id}`
- `GET /debug/articles`
- `GET /debug/clusters`

## Pipeline verification checklist
Use this sequence to validate the first success state:
1. Confirm worker is running and no startup errors in logs.
2. Hit `/debug/articles` and confirm Miniflux articles are ingested.
3. Hit `/api/clusters` and confirm clusters are returned with all required fields:
   - `headline`
   - `summary`
   - `what_changed`
   - `why_it_matters`
4. Hit `/debug/clusters` and verify any invalid clusters show validation reasons.
5. Hit `/metrics` and confirm required metrics exist:
   - `articles_ingested_total`
   - `articles_deduplicated_total`
   - `clusters_created_total`
   - `clusters_updated_total`
   - `last_ingest_time`
   - `last_cluster_time`

## Local commands
- Start stack: `make up`
- Stop stack: `make down`
- Tail logs: `make logs`
- Run migrations: `make migrate`
- Run one pipeline pass: `make run-once`
- Run tests: `make test`

## Deterministic clustering rules (v1)
Weighted score for each article->cluster candidate:
- Title similarity: 0.45
- Named entity overlap: 0.25
- Keyword overlap: 0.20
- Publication time proximity: 0.10

If the best score is below threshold, a new cluster is created.

## Notes
- This v1 intentionally avoids a polished frontend.
- No auth, personalization, notifications, or social integration.
- LLM summarization is not required for operation.
