# AGENTS.md

Project-wide instructions for Codex agents working in this repository.

## Project Intent

Roundup is a self-hosted news intelligence app. It ingests RSS/feed entries through Miniflux, filters and deduplicates articles, clusters related reporting, generates deterministic story fields, exposes FastAPI endpoints, and serves a React web UI.

Default stance: make small, production-minded changes that preserve Docker startup, existing API contracts, and the current backend architecture. Do not bundle redesigns with cleanup or hardening work.

## Repo Layout

- `app/`: FastAPI backend package.
- `app/main.py`: app creation, router registration, API index, metrics endpoint, startup checks.
- `app/api/routes/`: public API, debug, health, search, source, and article route handlers.
- `app/core/`: settings, logging, and startup validation.
- `app/db/`: SQLAlchemy base, models, engine, and session dependency.
- `app/schemas/`: Pydantic response contracts shared by API routes and frontend types.
- `app/services/`: ingestion, Miniflux client, normalization, content quality, clustering, enrichment, metrics, source health, serialization, topics, and validation.
- `alembic/`: Alembic environment and versioned migration files.
- `scripts/`: operational commands for Miniflux bootstrap, one-shot pipeline runs, demo checks, and cleanup helpers.
- `data/`: Miniflux seed feeds and demo/sample ingestion data.
- `frontend/`: Vite React app, nginx config, public UI, inspector UI, frontend tests, and frontend Dockerfile.
- `tests/`: backend pytest suite. Tests currently use SQLite fixtures for most app tests plus static migration checks.
- `docs/`: architecture notes, story contracts, database hygiene notes, and known issues.
- `docker-compose.yml`: local/self-hosted stack with `db`, `miniflux-db`, `miniflux`, `miniflux-bootstrap`, `migrate`, `api`, `worker`, and `inspector`.

## Docker Runtime

From the repo root:

```powershell
Copy-Item .env.example .env
docker compose config --quiet
docker compose up --build
```

Stop and remove local volumes when a clean boot is required:

```powershell
docker compose down -v
```

Useful runtime checks:

```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/api/clusters
curl.exe http://localhost:8000/api/clusters/homepage
curl.exe http://localhost:8000/api/sources
curl.exe http://localhost:8000/debug/clusters
curl.exe http://localhost:8000/metrics
```

Operational commands:

```powershell
docker compose run --rm migrate
docker compose run --rm worker python -m scripts.run_pipeline_once
docker compose exec api python scripts/demo_cluster_promotion.py
```

The public UI is `http://localhost:8080/`. The operator inspector is `http://localhost:8080/inspect`.

## Tests, Type Checks, Linting, Build

Backend tests:

```powershell
pytest -q
```

Targeted backend test example:

```powershell
pytest -q tests/test_clustering.py
```

Frontend tests and production build:

```powershell
cd frontend
npm.cmd test -- --run
npm.cmd run build
```

Frontend dependency audit:

```powershell
cd frontend
npm.cmd audit --audit-level=moderate
```

There is currently no dedicated backend lint command, backend type-check command, or frontend lint command configured. Do not claim lint or type-check success unless a real command was run. Frontend TypeScript checking runs as part of `npm.cmd run build`.

On this Windows machine, prefer `npm.cmd` instead of `npm` in PowerShell.

## Required Verification Before Claiming Success

Run the narrowest relevant checks for the change, and report exact commands plus results.

- Documentation-only change: no runtime tests required unless commands or contracts were changed; still inspect the edited document.
- Backend behavior change: run targeted pytest files and `pytest -q` unless the change is trivial.
- Migration/model/API schema change: run `pytest -q` and `docker compose run --rm migrate`.
- Docker/startup change: run `docker compose config --quiet`, `docker compose up --build`, then check `curl.exe http://localhost:8000/health`.
- Ingestion or Miniflux change: run backend tests and, when Docker is available, `docker compose run --rm worker python -m scripts.run_pipeline_once`.
- Clustering change: run `pytest -q tests/test_clustering.py tests/test_cluster_promotion.py tests/test_debug.py` and then `pytest -q` when risk is not trivial.
- Frontend change: run `cd frontend; npm.cmd test -- --run` and `cd frontend; npm.cmd run build`.
- API/frontend contract change: verify backend tests plus frontend tests/build, and update `frontend/src/types.ts` with API client usage.

If Docker is unavailable, blocked, or local ports are occupied, say exactly which Docker command was skipped and why.

Before finishing, audit your own diff critically:

- Did this introduce a breaking API, schema, config, migration, Docker, or frontend route change?
- Are there missing field, null, empty-list, timezone, malformed-feed, or stale-ID risks?
- Does this conflict with existing ingestion filters, promotion gates, or clustering gates?
- What edge cases still fail or remain untested?
- Where does the change appear in the UI or API? Provide an endpoint, URL, or curl command and the field expected to change.

## Migration Rules

- Use short Alembic revision IDs, for example `0012_source_controls`; do not use long generated hashes.
- Every schema change must include the Alembic migration, SQLAlchemy model update, serializer/schema/API update if exposed, and tests.
- Migrations must be reversible unless the PR explicitly documents why not.
- Do not wipe user data, truncate tables, reset sequences, rebuild clusters, or delete articles inside a migration.
- For non-null columns on existing tables, add a safe default/backfill path before enforcing non-null behavior.
- Avoid importing mutable application service logic from migrations. If a migration needs data transformation logic, freeze the minimal helper code inside the migration.
- Keep migration PRs narrow. Do not combine schema work with frontend redesign or broad clustering rewrites.

## Docker And Startup Rules

- Preserve the Compose startup chain: Postgres and Miniflux health, Miniflux bootstrap, Alembic migration, API and worker, then frontend/nginx.
- A clean `docker compose up --build` must work after copying `.env.example` to `.env`.
- `/health` must be honest: optional integration failures may be `degraded`, but database failure must not appear healthy.
- Do not move scheduled ingestion into API startup. The `worker` service owns scheduled pipeline execution.
- Keep Docker defaults conservative for self-hosted installs: local bind addresses, one API worker, one scheduler, one nginx worker unless explicitly changed.
- Do not expose debug, metrics, database, or admin surfaces as production-safe defaults.

## Ingestion And Miniflux Rules

- Bad feed seed URLs must warn and continue; they must not break startup unless every usable seed fails.
- Validate feed URLs before importing. Reject unsafe schemes, localhost/private IP hosts, URL credentials, and secret query parameters unless `ROUNDUP_ALLOW_PRIVATE_FEED_URLS=true`.
- Do not reintroduce a global latest-100 ingestion cap.
- Prefer per-feed limits, lookback windows, dedupe, and category/source balancing.
- Service journalism, affiliate finance, stale evergreen content, and low-trust aggregators must remain explicit and inspectable in logs, metrics, and debug routes.
- Miniflux failures should be isolated per source where practical; one bad feed should not take down a full run.
- Preserve the live Miniflux default path. Demo/sample mode must remain explicit through `DEMO_MODE=true`.

## Clustering Rules

- Do not rewrite the clustering architecture unless the user explicitly asks for a redesign.
- Prefer stricter gates and targeted regression fixtures over broad heuristic churn.
- Time proximity must not override failed semantic, entity, or content-class gates.
- For marginal decisions, prefer creating a new hidden/candidate cluster over contaminating an existing story.
- Ordinary joins should remain entity-driven unless a same-source update chain or near-duplicate title path is explicitly satisfied.
- Keep debug explainability: join decisions, thresholds, warning codes, rejection reasons, promotion blockers, source-quality reasons, and ignored/used features must remain visible in inspector/debug routes.
- Do not expose internal debug-only reasoning in public story pages.

## Frontend Rules

- Do not redesign the UI during cleanup, hardening, backend, ingestion, Docker, or clustering tasks.
- Keep `/` as the public product surface and `/inspect` as the operator/debug surface.
- Use live API data; do not hardcode mock news into production components.
- Hide weak or empty public sections rather than filling them with fake placeholders, but do not hide valid API stories solely because media is missing unless the task explicitly asks for that behavior.
- Keep public story pages free of debug-only clustering reasoning.
- If API contracts change, update `frontend/src/types.ts`, `frontend/src/api/client.ts`, page/component usage, and tests in the same PR.
- Use `rel="noreferrer"` for external links opened in a new tab.

## Security Rules

- Do not commit secrets, API keys, real passwords, bearer tokens, private feed URLs, `.env`, database dumps, or Miniflux API key files.
- Keep `.env.example` safe and documented with placeholder values only.
- Validate and sanitize public feed/source URLs before returning them through APIs.
- Keep debug, metrics, database ports, and Miniflux/admin surfaces local-only by default.
- Logging must redact tokens, passwords, API keys, Authorization values, and URL credentials.

## PR And Handoff Expectations

Each PR or handoff must include:

- Short summary of what changed and why.
- Files or areas touched.
- Exact tests, builds, migrations, Docker commands, and curl checks run with results.
- Known risks, skipped checks, or follow-up work.
- UI/API inspection evidence: endpoint or URL, field to inspect, and what should look different.
- Confirmation that unrelated refactors were not bundled.

Keep diffs small. If the task crosses backend schema, ingestion, clustering, frontend, and Docker, split it into ordered PRs unless the user explicitly asks for one combined change.
