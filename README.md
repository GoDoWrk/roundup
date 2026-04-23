# Roundup

Roundup is a backend-first, self-hosted news intelligence pipeline. It ingests news entries, deduplicates them, clusters related coverage into strict story objects, and exposes those objects through typed APIs and a thin inspection UI.

## Core capabilities
- FastAPI API with typed cluster/article/debug responses.
- Postgres persistence with Alembic migrations.
- Worker scheduler for recurring ingestion + clustering.
- Deterministic clustering/enrichment/validation (no LLM requirement).
- Prometheus-style metrics plus debug endpoints.
- Read-only inspection frontend at `http://localhost:8081`.

## Repository structure
- `app/` API, services, models, config, startup checks.
- `alembic/` migration history.
- `frontend/` React/Vite inspection interface.
- `data/sample_miniflux_entries.json` optional offline dev ingestion data.
- `tests/` backend test coverage.
- `docs/architecture.md` architecture notes.
- `OPERATIONS.md` day-to-day runbook to verify pipeline health.

## Environment and startup checks
Copy `.env.example` to `.env`.

Worker startup requires one ingestion source:
1. Live Miniflux: `MINIFLUX_URL` + `MINIFLUX_API_KEY`.
2. Offline sample data: `SAMPLE_MINIFLUX_DATA_PATH`.

If neither is configured, worker startup fails fast with a clear error message.

Key ingestion settings:
- `MINIFLUX_URL`
- `MINIFLUX_API_KEY`
- `MINIFLUX_FETCH_LIMIT`
- `MINIFLUX_TIMEOUT_SECONDS`
- `SAMPLE_MINIFLUX_DATA_PATH`

## Docker and migration flow
`docker-compose.yml` now uses a dedicated migration service:
1. `db` starts and passes healthcheck.
2. `migrate` runs `alembic upgrade head` once.
3. `api` and `worker` start only after migration success.
4. `inspector` starts after API healthcheck passes.

This avoids migration race conditions between API and worker containers.

## Quick start
1. Create env file:
   ```bash
   cp .env.example .env
   ```
2. Start stack:
   ```bash
   docker compose up --build
   ```
3. Check API health:
   ```bash
   curl http://localhost:8000/health
   ```
4. Open inspector:
   - `http://localhost:8081`

## Required API endpoints
- `GET /health`
- `GET /metrics`
- `GET /api/articles`
- `GET /api/clusters`
- `GET /api/clusters/{cluster_id}`
- `GET /debug/articles`
- `GET /debug/clusters`

## Metrics to verify
- `articles_ingested_total`
- `articles_deduplicated_total`
- `articles_malformed_total`
- `ingest_source_failures_total`
- `clusters_created_total`
- `clusters_updated_total`
- `cluster_candidates_evaluated_total`
- `cluster_signal_rejected_total`
- `cluster_attach_decisions_total`
- `cluster_new_decisions_total`
- `cluster_low_confidence_new_total`
- `cluster_validation_rejected_total`
- `cluster_timeline_events_deduplicated_total`
- `last_ingest_time`
- `last_cluster_time`

## Local commands
- `make up` start full stack.
- `make down` stop stack.
- `make logs` follow service logs.
- `make migrate` run migrations manually.
- `make run-once` run one worker pipeline cycle.
- `make test` run backend tests.
- `make frontend-test` run frontend tests.

## Inspection UI routes
- `/` cluster list + debug-only invalid cluster panel.
- `/clusters/:clusterId` full cluster detail or debug fallback if filtered from main API.
- `/metrics` parsed pipeline metrics with optional auto-refresh.
