# Roundup

Roundup is a backend-first, self-hosted news intelligence pipeline. It ingests news entries, deduplicates them, groups related coverage into story clusters, and exposes those clusters through typed APIs plus a read-only inspection UI.

## What's in the repo
- `app/` FastAPI app, clustering services, models, config, and startup checks.
- `alembic/` database migrations.
- `frontend/` Vite/React inspector and public story UI.
- `data/` seed feeds and demo ingestion data.
- `tests/` backend test coverage.
- `docs/architecture.md` implementation notes.
- `OPERATIONS.md` quick health-check runbook.

## Core features
- FastAPI API with typed cluster, article, and debug responses.
- Postgres persistence with Alembic migrations.
- Worker scheduler for recurring ingestion and clustering.
- Deterministic clustering, enrichment, and validation.
- Built-in Miniflux provisioning and feed seeding on first startup.
- Metrics and debug endpoints for operator visibility.
- Public homepage plus a separate inspector surface.

## Quick start
1. Copy the environment file:
   ```bash
   cp .env.example .env
   ```
2. Start the stack:
   ```bash
   docker compose up --build
   ```
3. Check the API:
   ```bash
   curl http://localhost:8000/health
   ```
4. View the public UI:
   - `http://localhost:8080`

## Runtime modes
Default mode uses live Miniflux:
- `DEMO_MODE=false`
- `MINIFLUX_URL=http://miniflux:8080`
- `MINIFLUX_API_KEY_FILE` is written automatically by bootstrap

Demo mode is explicit:
- Set `DEMO_MODE=true`
- Keep `SAMPLE_MINIFLUX_DATA_PATH` pointed at a valid JSON file

If live Miniflux is required and credentials are missing, the worker fails fast with a clear error.

Important ingestion settings:
- `MINIFLUX_URL`
- `MINIFLUX_API_KEY` optional manual override
- `MINIFLUX_API_KEY_FILE` auto-generated in Docker flow
- `MINIFLUX_FETCH_LIMIT`
- `MINIFLUX_TIMEOUT_SECONDS`
- `DEMO_MODE`

## Startup flow
`docker-compose.yml` uses a dedicated migration/bootstrap sequence:
1. `db` becomes healthy.
2. `miniflux-db` and `miniflux` become healthy.
3. `miniflux-bootstrap` runs once to create/reuse a Miniflux API key and import starter feeds.
4. `migrate` runs `alembic upgrade head`.
5. `api` and `worker` start after bootstrap and migrations succeed.
6. `inspector` starts after the API healthcheck passes.

This keeps schema changes and Miniflux setup from racing the app startup.

## Useful endpoints
- `GET /health`
- `GET /metrics`
- `GET /api/articles`
- `GET /api/clusters`
- `GET /api/clusters/{cluster_id}`
- `GET /debug/articles`
- `GET /debug/clusters`

## Public routes
- `/` public homepage with live story cards from `/api/clusters`.
- `/story/:clusterId` public story detail view.
- `/inspect` operator cluster list and debug-only rejected clusters.
- `/inspect/clusters/:clusterId` full cluster detail or debug fallback.
- `/inspect/metrics` pipeline metrics with optional auto-refresh.

## Useful commands
- `make up` start the full stack.
- `make down` stop the stack.
- `make logs` follow service logs.
- `make migrate` run migrations manually.
- `make run-once` run one worker pipeline cycle.
- `make purge-demo-data` remove demo-seeded `demo.roundup.local` rows and orphaned clusters.
- `make test` run backend tests.
- `make frontend-test` run frontend tests.

Optional deterministic lifecycle check:
```bash
docker compose exec api python scripts/demo_cluster_promotion.py
```

## Fresh install verification
Use this sequence before release or PR handoff to confirm a clean checkout can build, migrate, and serve the expected UI/API surfaces:

```bash
cp .env.example .env
docker compose build
docker compose -p roundup_migration_test up -d db
docker compose -p roundup_migration_test run --rm migrate
docker compose -p roundup_migration_test down -v
docker compose up --build
```

Then inspect:

```bash
curl http://localhost:8000/health
curl "http://localhost:8000/api/clusters?limit=5"
curl "http://localhost:8000/api/search?q=transit&limit=5"
curl http://localhost:8000/debug/articles
curl http://localhost:8000/debug/clusters
```

Public UI routes should render at `http://localhost:8080/`, `/saved`, `/search`, `/alerts`, and `/inspect`. Story detail can be opened with any `cluster_id` returned from `/api/clusters`.

## What to watch
Promoted clusters in `/debug/clusters` expose:
- `visibility_threshold`
- `promotion_eligible`
- `promoted_at`
- `previous_status`
- `promotion_reason`
- `promotion_explanation`

Pipeline metrics worth checking:
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
