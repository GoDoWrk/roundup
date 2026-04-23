# Roundup

Roundup is a backend-first, self-hosted news intelligence pipeline. It ingests news entries, deduplicates them, clusters related coverage into strict story objects, and exposes those objects through typed APIs and a thin inspection UI.

## Core capabilities
- FastAPI API with typed cluster/article/debug responses.
- Postgres persistence with Alembic migrations.
- Worker scheduler for recurring ingestion + clustering.
- Built-in Miniflux provisioning and feed seeding on first startup.
- Deterministic clustering/enrichment/validation (no LLM requirement).
- Prometheus-style metrics plus debug endpoints.
- Read-only inspection frontend at `http://localhost:8080`.

## Repository structure
- `app/` API, services, models, config, startup checks.
- `alembic/` migration history.
- `frontend/` React/Vite inspection interface.
- `data/miniflux_seed_feeds.json` default Miniflux starter feeds imported at bootstrap.
- `data/sample_miniflux_entries.json` demo-mode ingestion data.
- `tests/` backend test coverage.
- `docs/architecture.md` architecture notes.
- `OPERATIONS.md` day-to-day runbook to verify pipeline health.

## Environment and startup checks
Copy `.env.example` to `.env`.

Default mode is live Miniflux:
- `DEMO_MODE=false`
- `MINIFLUX_URL` points to the internal service (`http://miniflux:8080`)
- `MINIFLUX_API_KEY_FILE` is written automatically by the bootstrap service

Demo mode is explicit:
- Set `DEMO_MODE=true`
- Keep `SAMPLE_MINIFLUX_DATA_PATH` set to a valid JSON file

If live Miniflux is required and credentials are missing, worker startup fails fast with a clear error.

Key ingestion settings:
- `MINIFLUX_URL`
- `MINIFLUX_API_KEY` (optional manual override)
- `MINIFLUX_API_KEY_FILE` (auto-generated in Docker flow)
- `MINIFLUX_FETCH_LIMIT`
- `MINIFLUX_TIMEOUT_SECONDS`
- `DEMO_MODE`

## Docker and migration flow
`docker-compose.yml` now uses a dedicated migration service:
1. `db` starts and passes healthcheck.
2. `miniflux-db` and `miniflux` start and pass healthchecks.
3. `miniflux-bootstrap` runs once:
   - verifies admin credentials
   - creates/reuses a Miniflux API key
   - writes key to shared file for Roundup
   - imports curated starter feeds
4. `migrate` runs `alembic upgrade head` once.
5. `api` and `worker` start only after migrate + bootstrap succeed.
6. `inspector` starts after API healthcheck passes.

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
4. Trigger one immediate pipeline run (optional):
   ```bash
   docker compose exec api python scripts/run_pipeline_once.py
   ```
5. Check clusters:
   ```bash
   curl http://localhost:8000/api/clusters
   ```
6. Open inspector:
   - `http://localhost:8080`

## Automatic Miniflux provisioning
On a fresh stack, `miniflux-bootstrap` provisions Miniflux with minimal input:
- waits until Miniflux is reachable
- authenticates with `MINIFLUX_ADMIN_USERNAME` and `MINIFLUX_ADMIN_PASSWORD`
- creates/reuses API key and saves it to `MINIFLUX_API_KEY_FILE`
- imports feeds from `MINIFLUX_BOOTSTRAP_FEEDS_FILE` (default curated file in `data/`)
- requests an initial refresh

If bootstrap fails, `api` and `worker` do not start, and logs show a clear failure reason.

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
- `clusters_promoted_total`
- `clusters_hidden_total`
- `clusters_active_total`
- `cluster_promotion_attempts_total`
- `cluster_promotion_failures_total`
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

Promotion lifecycle demo (local deterministic check):
- `docker compose exec api python scripts/demo_cluster_promotion.py`
- output shows phase 1 (hidden), phase 2 (hidden), phase 3 (promoted) for the same `cluster_id`.

Hidden to active promotion visibility in `/debug/clusters`:
- `visibility_threshold`
- `promotion_eligible`
- `promoted_at`
- `previous_status`
- `promotion_reason`
- `promotion_explanation`

## Frontend routes
- `/` public homepage with live story cards from `/api/clusters`.
- `/story/:clusterId` public story detail view with structured live cluster data.
- `/inspect` cluster list + debug-only invalid cluster panel.
- `/inspect/clusters/:clusterId` full cluster detail or debug fallback if filtered from main API.
- `/inspect/metrics` parsed pipeline metrics with optional auto-refresh.
