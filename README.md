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
- Compose binds API, UI, and Postgres to `127.0.0.1` by default. Set `ROUNDUP_BIND_HOST=0.0.0.0` only when you intentionally want API/UI access from other machines.

Demo mode is explicit:
- Set `DEMO_MODE=true`
- Keep `SAMPLE_MINIFLUX_DATA_PATH` pointed at a valid JSON file

If live Miniflux is required and credentials are missing, the worker fails fast with a clear error.

Important ingestion settings:
- `MINIFLUX_URL`
- `MINIFLUX_API_KEY` optional manual override
- `MINIFLUX_API_KEY_FILE` auto-generated in Docker flow
- `MINIFLUX_TIMEOUT_SECONDS`
- `MINIFLUX_REQUEST_RETRIES`: transient Miniflux request retries used by the worker. Default `2`.
- `ROUNDUP_INGEST_MAX_TOTAL_ARTICLES`: max entries sent into one ingestion run after per-feed/category balancing. Default `1000`. Legacy `MINIFLUX_FETCH_LIMIT` is still accepted as an alias.
- `ROUNDUP_INGEST_MAX_ARTICLES_PER_FEED`: max recent entries considered from each active Miniflux feed. Default `10`.
- `ROUNDUP_INGEST_LOOKBACK_HOURS`: ignore feed entries older than this window. Default `24`.
- `ROUNDUP_INGEST_MAX_PAGES`: max Miniflux pages to request per feed. Default `10`.
- `ROUNDUP_INGEST_CATEGORY_QUOTAS_ENABLED`: round-robin candidate selection across feed categories before applying the total cap. Default `true`.
- `ROUNDUP_ALLOW_PRIVATE_FEED_URLS`: allows localhost/private-network feed URLs during bootstrap when set to `true`. Keep `false` unless you intentionally ingest from internal RSS services.
- `MINIFLUX_BOOTSTRAP_REFRESH_WAIT_SECONDS`: after seed import, wait briefly for Miniflux to expose at least one refreshed entry. Empty results warn and continue. Default `45`.
- `DEMO_MODE`

Security notes:
- `.env.example` contains local placeholders only. Change database and Miniflux admin passwords before exposing the stack beyond localhost.
- Feed seed URLs with credentials, secret query parameters, unsafe schemes, or localhost/private IP hosts are rejected unless private feed URLs are explicitly enabled.
- `/debug/*` and `/metrics` are operator endpoints. They are available through the local UI proxy by default and should not be exposed directly to the public internet.

## Runtime sizing
Defaults are conservative for small self-hosted machines. Docker Compose starts one API process, one scheduler process, and one nginx inspector worker unless you opt into more.

Runtime knobs:
- `API_WORKERS`: uvicorn worker processes for the API. Default `1`.
- `INSPECTOR_WORKER_PROCESSES`: nginx worker processes for the UI container. Default `1`; this prevents nginx `worker_processes auto` from spawning one worker per host CPU.
- `SCHEDULER_ENABLED`: enables the dedicated worker scheduler. Default `true`.
- `SCHEDULER_INTERVAL_SECONDS`: delay between ingestion/clustering cycles. Default `600`.
- `INGESTION_CONCURRENCY`: reserved ingestion concurrency limit. Default `1`.
- `SUMMARIZATION_CONCURRENCY`: reserved summarization/enrichment concurrency limit. Default `1`.
- `CLUSTERING_BATCH_SIZE`: max unclustered articles processed per scheduler cycle. Default `100`.
- `CLUSTERING_CONCURRENCY`: reserved clustering concurrency limit. Default `1`.

Recommended profiles:
- Raspberry Pi / low power: `ROUNDUP_INGEST_MAX_TOTAL_ARTICLES=300`, `ROUNDUP_INGEST_MAX_ARTICLES_PER_FEED=5`, `ROUNDUP_INGEST_LOOKBACK_HOURS=12`, `API_WORKERS=1`, `INSPECTOR_WORKER_PROCESSES=1`, `INGESTION_CONCURRENCY=1`, `SUMMARIZATION_CONCURRENCY=1`, `CLUSTERING_BATCH_SIZE=50`, `CLUSTERING_CONCURRENCY=1`.
- Normal self-hosted: `ROUNDUP_INGEST_MAX_TOTAL_ARTICLES=1000`, `ROUNDUP_INGEST_MAX_ARTICLES_PER_FEED=10`, `ROUNDUP_INGEST_LOOKBACK_HOURS=24`, `API_WORKERS=1`, `INSPECTOR_WORKER_PROCESSES=1`, `INGESTION_CONCURRENCY=1`, `SUMMARIZATION_CONCURRENCY=1`, `CLUSTERING_BATCH_SIZE=100`, `CLUSTERING_CONCURRENCY=1`.
- High-volume install: `ROUNDUP_INGEST_MAX_TOTAL_ARTICLES=2500`, `ROUNDUP_INGEST_MAX_ARTICLES_PER_FEED=20`, `ROUNDUP_INGEST_LOOKBACK_HOURS=36`, `ROUNDUP_INGEST_MAX_PAGES=15`, `API_WORKERS=2`, `INSPECTOR_WORKER_PROCESSES=2`, `INGESTION_CONCURRENCY=2`, `SUMMARIZATION_CONCURRENCY=2`, `CLUSTERING_BATCH_SIZE=250`, `CLUSTERING_CONCURRENCY=2`.

Only the `worker` service runs scheduled ingestion. API workers do not run scheduled jobs. The scheduler also uses a Postgres advisory lock, so accidental duplicate worker replicas skip cycles while another scheduler owns the lock.

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
- `GET /api/clusters/homepage`
- `GET /api/clusters/{cluster_id}`
- `GET /api/sources`
- `GET /debug/articles`
- `GET /debug/clusters`

`GET /health` also reports runtime sizing and ingestion status in `runtime`, including API workers, inspector workers, scheduler state, concurrency settings, clustering batch size, and whether ingestion is active.

## Public routes
- `/` public homepage with Top Stories, Developing Stories, and Just In sections from `/api/clusters/homepage`.
- `/story/:clusterId` public story detail view.
- `/saved` browser-local saved story list.
- `/search` direct search route, kept out of primary navigation until search becomes core.
- `/settings` browser-local display preferences and source health.
- `/inspect` operator cluster list and debug-only rejected clusters.
- `/inspect/clusters/:clusterId` full cluster detail or debug fallback.

Frontend API routing:
- Docker/nginx serves the UI and proxies `/api`, `/debug`, `/metrics`, and `/health` to the API container.
- Local Vite dev uses the same route prefixes and proxies them to `http://localhost:8000`.
- Set `VITE_ROUNDUP_API_BASE_URL=http://localhost:8000` only when intentionally serving the frontend from a different origin without the Vite/nginx proxy.
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
curl http://localhost:8000/api/clusters/homepage
curl "http://localhost:8000/api/search?q=transit&limit=5"
curl http://localhost:8000/api/sources
curl http://localhost:8000/debug/articles
curl http://localhost:8000/debug/clusters
```

Public UI routes should render at `http://localhost:8080/`, `/saved`, `/search`, and `/inspect`. `/alerts` redirects to `/saved` because alerts/followed stories are not exposed until real notification behavior exists. Story detail can be opened with any public `cluster_id` returned from `/api/clusters` or `/api/clusters/homepage`.

## Homepage promotion settings
The public homepage keeps promoted stories quality-controlled while still showing current activity:
- `CLUSTER_MIN_SOURCES_FOR_TOP_STORIES` controls Top Stories promotion.
- `CLUSTER_MIN_DISTINCT_SOURCES_FOR_API` keeps repeated same-source updates from being promoted as confirmed multi-source stories.
- `CLUSTER_MIN_SOURCES_FOR_DEVELOPING_STORIES` controls Developing Stories.
- `CLUSTER_SHOW_JUST_IN_SINGLE_SOURCE` allows single-source candidate stories in Just In without promoting them as confirmed Top Stories.
- `CLUSTER_HOMEPAGE_TOP_LIMIT`, `CLUSTER_HOMEPAGE_DEVELOPING_LIMIT`, and `CLUSTER_HOMEPAGE_JUST_IN_LIMIT` cap each section.

## What to watch
Promoted clusters in `/debug/clusters` expose:
- `visibility_threshold`
- `promotion_eligible`
- `promoted_at`
- `previous_status`
- `promotion_reason`
- `promotion_explanation`

Pipeline metrics worth checking:
- `configured_feed_count`
- `active_feed_count`
- `feeds_checked`
- `feeds_with_new_articles`
- `miniflux_entries_seen`
- `articles_fetched_raw`
- `latest_articles_fetched`
- `latest_articles_stored`
- `latest_duplicate_articles_skipped`
- `latest_articles_malformed`
- `articles_rejected_quality`
- `articles_rejected_stale`
- `articles_rejected_service_finance`
- `latest_failed_source_count`
- `latest_candidate_clusters_created`
- `latest_clusters_updated`
- `latest_clusters_hidden`
- `latest_clusters_promoted`
- `latest_visible_clusters`
- `articles_pending_clustering`
- `summaries_pending`
- `active_sources`
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
