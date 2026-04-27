# AGENTS.md

Project-wide instructions for Codex agents working in this repository.

## Project Intent

Roundup is a self-hosted news intelligence app. It ingests RSS/feed entries through Miniflux, filters and deduplicates articles, clusters related reporting, generates deterministic story fields, exposes FastAPI endpoints, and serves a React web UI.

Default stance: make small, production-minded changes that preserve Docker startup, existing API contracts, and the current backend architecture.

## Repo Layout

- `app/`: FastAPI backend, SQLAlchemy models, config, API routes, ingestion, clustering, metrics, and serialization.
- `app/api/routes/`: public API, debug, health, search, and source endpoints.
- `app/services/`: ingestion, Miniflux client, normalization, content quality, clustering, enrichment, metrics, source health, and serialization logic.
- `app/db/`: SQLAlchemy base, models, and session setup.
- `app/schemas/`: Pydantic API response contracts.
- `alembic/`: database migration environment and versioned revisions.
- `scripts/`: operational commands such as Miniflux bootstrap, one-shot pipeline run, demo checks, and cleanup helpers.
- `data/`: seed feeds and sample/demo ingestion data.
- `frontend/`: Vite React app served by nginx in Docker.
- `tests/`: backend pytest suite.
- `docs/`: architecture notes, story contract notes, and known issues.
- `docker-compose.yml`: local/self-hosted stack: Postgres, Miniflux, bootstrap, migration job, API, worker, and frontend/nginx.

## Local Runtime Commands

From the repo root:

```powershell
Copy-Item .env.example .env
docker compose up --build
docker compose down -v
```

Useful operational checks:

```powershell
docker compose config --quiet
docker compose run --rm migrate
docker compose run --rm worker python -m scripts.run_pipeline_once
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/api/clusters
curl.exe http://localhost:8000/debug/clusters
curl.exe http://localhost:8000/metrics
```

The public UI is at `http://localhost:8080/`. The inspector is under `http://localhost:8080/inspect`.

## Test And Build Commands

Backend tests:

```powershell
pytest -q
```

Frontend tests and production build:

```powershell
cd frontend
npm.cmd test -- --run
npm.cmd run build
```

There is currently no dedicated backend lint or type-check command configured. Do not claim lint/type-check success unless a real command was added or run. Frontend type checking runs as part of `npm.cmd run build`.

## Required Verification Before Claiming Success

Run the narrowest relevant checks for the change, and report exact commands and results.

- Backend behavior change: run targeted pytest files plus `pytest -q` when risk is not trivial.
- Migration/model/API change: run `pytest -q` and `docker compose run --rm migrate`.
- Docker/startup change: run `docker compose config --quiet`, `docker compose up --build`, then check `/health`.
- Ingestion or clustering change: run backend tests plus a one-shot worker pipeline when Docker is available.
- Frontend change: run `npm.cmd test -- --run` and `npm.cmd run build`.
- API/frontend contract change: verify both backend tests and frontend tests/build.

Before finishing, audit your own diff:

- Did this introduce a breaking API, schema, config, or migration change?
- Are there missing field, null, empty-list, timezone, or malformed-feed risks?
- Does it conflict with existing ingestion or clustering gates?
- What edge cases still fail or remain untested?

## Migration Rules

- Use short Alembic revision IDs, for example `0011_source_controls`, not long generated hashes.
- Every schema change must include the Alembic migration, SQLAlchemy model update, serializer/schema/API update if exposed, and tests.
- Migrations must be reversible unless there is a documented reason they cannot be.
- Do not wipe user data, truncate tables, reset sequences, or rebuild clusters inside a migration.
- For non-null columns on existing tables, add a safe default/backfill path.
- Keep migration PRs narrow. Do not combine schema work with frontend redesign or broad clustering rewrites.

## Docker And Startup Rules

- Preserve the Compose startup chain: DB and Miniflux health, Miniflux bootstrap, Alembic migration, API/worker, then frontend.
- A clean `docker compose up --build` must work from `.env.example` copied to `.env`.
- `/health` must be honest: degraded integrations may report `degraded`, but database failure must not look healthy.
- Do not move scheduled ingestion into API startup. The worker owns scheduler execution.
- Keep Docker defaults conservative for self-hosted installs.

## Ingestion And Miniflux Rules

- Bad feed seed URLs must warn and continue; they must not break startup unless every usable seed fails.
- Validate feed URLs before importing; reject localhost, private IPs, credentials in URLs, and unsafe schemes.
- Do not reintroduce a global latest-100 ingestion cap.
- Prefer per-feed limits, lookback windows, dedupe, and category/source balancing.
- Service, affiliate, stale evergreen, and low-trust aggregator handling must remain explicit and inspectable.
- Miniflux failures should be isolated per source where practical; one bad feed should not take down the run.

## Clustering Rules

- Do not rewrite the clustering architecture unless the user explicitly asks for a redesign.
- Prefer stricter gates and new regression fixtures over broad heuristic churn.
- Time proximity must not override failed semantic/entity/content-class gates.
- For marginal cases, prefer a new hidden/candidate cluster over contaminating an existing story.
- Preserve debug explainability: join decisions, thresholds, warnings, rejection reasons, and promotion blockers should remain visible in inspector/debug routes.
- Do not expose internal debug reasoning in public story pages.

## Frontend Rules

- Do not redesign the UI during cleanup, hardening, backend, ingestion, or clustering tasks.
- Keep `/` as the public product surface and `/inspect` as the operator/debug surface.
- Use live API data; do not hardcode mock news into production components.
- Hide weak or empty public sections rather than filling them with fake placeholders.
- If API contracts change, update `frontend/src/types.ts`, client usage, and tests in the same PR.

## Security Rules

- Do not commit secrets, API keys, real passwords, tokens, or private feed URLs.
- Keep `.env` local-only; update `.env.example` with safe documented defaults.
- Avoid exposing debug, metrics, database ports, or admin surfaces as production-safe defaults.
- Sanitize public feed/source URLs before returning them through APIs.
- Use `rel="noreferrer"` for external links opened in a new tab.

## PR Expectations

Each PR or handoff should include:

- Short summary of what changed and why.
- Files/areas touched.
- Exact tests/builds/migrations run and their results.
- Known risks, skipped checks, or follow-up work.
- Confirmation that unrelated refactors were not bundled.

Keep diffs small. If the task crosses backend schema, ingestion, clustering, frontend, and Docker, split it into ordered PRs unless the user explicitly asks for one combined change.
