# AGENTS.md

This file defines project-wide working agreements for Codex agents and human contributors operating in this repository.

## Project intent
Roundup is a self-hosted news intelligence app aimed at a polished, consumer-facing news experience (Google News-like) centered on story clusters, timelines, summaries, sources, and story evolution over time.

When making changes, prioritize Docker-friendly operation, straightforward installation, and long-term maintainability.

## Scope and PR discipline
1. Keep PRs narrowly scoped. Do not mix backend schema work, frontend redesign, and unrelated cleanup in one PR.
2. Do not remove existing working backend functionality unless it is clearly replaced and tested.
3. Prefer incremental migration over rewrites.

## Platform and runtime guarantees
4. Preserve Docker Compose workflows (`docker-compose.yml`, service startup order, and migration flow).
5. Preserve `/health` and existing inspector/debug routes unless explicitly instructed otherwise.

## Data and UX expectations
6. Use real API data with graceful fallbacks. Do not hardcode mock news content into production components.
7. Frontend should be polished, responsive, and app-like, but must not depend on fake static data when API data exists.

## Database change protocol
8. Any new database field must include all of the following in the same PR:
   - Alembic migration
   - SQLAlchemy model update
   - schema/serializer/API surface update
   - automated test coverage for the new behavior

## Testing and reporting requirements
9. Add or update tests for any behavior change.
10. After changes, run relevant backend and frontend tests/builds and report exact commands and results.

## Repository-specific setup and verification guidance
Use these commands and flows as the default unless a task explicitly requires alternatives.

### Environment setup
- Copy env file: `cp .env.example .env`
- Start full stack: `docker compose up --build` (or `make up`)
- Stop stack: `docker compose down -v` (or `make down`)

### Migrations and pipeline
- Run migrations service: `docker compose run --rm migrate` (or `make migrate`)
- Trigger one pipeline run: `docker compose run --rm worker python -m scripts.run_pipeline_once` (or `make run-once`)

### Health and key endpoints
- Health check: `curl http://localhost:8000/health`
- Clusters API: `curl http://localhost:8000/api/clusters`
- Debug routes to preserve:
  - `GET /debug/articles`
  - `GET /debug/clusters`

### Tests
- Backend tests: `pytest -q` (or `make test`)
- Frontend tests: `cd frontend && npm test` (or `make frontend-test`)
- If frontend behavior changes, also run a production build check: `cd frontend && npm run build`

## Change safety checklist (before opening PR)
- Confirm no unrelated refactors or cleanup were bundled.
- Confirm Docker Compose workflow still works.
- Confirm `/health` and debug/inspector routes still function.
- Confirm data flows from real APIs or documented graceful fallbacks.
- Confirm all required tests were updated and executed, with exact command output summarized in the PR.
