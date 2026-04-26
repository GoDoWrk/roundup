# Roundup Architecture Note

## Why this design
Roundup v1 is intentionally backend-first and deterministic. The objective is a boring, inspectable pipeline that can ingest articles from Miniflux, store and deduplicate them, cluster related coverage, and expose validated story objects through an API.

## Major components
- **FastAPI API service**: exposes health, metrics, public cluster/article APIs, and debug visibility.
- **Worker service**: runs the interval scheduler and executes ingestion + clustering pipeline.
- **Postgres**: source of truth for articles, clusters, timeline events, and persistent pipeline counters.
- **Miniflux stack**: built-in `miniflux-db` + `miniflux` services for real feed aggregation.
- **Miniflux bootstrap job**: one-shot provisioning that verifies admin auth, creates/reuses an API key, imports seed feeds, and writes the token file consumed by API/worker.

## Pipeline shape
1. Pull entries from Miniflux (`/v1/entries`).
2. Normalize article text/metadata into deterministic features.
3. Deduplicate on stable `dedupe_hash`.
4. Cluster unclustered articles using deterministic weighted heuristics.
5. Enrich strict cluster fields with deterministic templates.
6. Validate required cluster text fields and mark invalid clusters.
7. Keep below-threshold or invalid clusters in hidden/debug-only state.
8. Promote the same cluster object to visible API state after it reaches source threshold and passes validation.
9. Expose only valid visible clusters in `/api/clusters`, with hidden lifecycle state visible in `/debug/clusters`.

## Determinism and observability choices
- No LLM dependency for clustering or required enrichment fields.
- Required text fields are never blank; deterministic fallback text is always available.
- Metrics are persisted in DB-backed counters so `/metrics` is consistent across multiple containers.
- Debug endpoints expose internal state to verify behavior without guesswork.

## Self-hosted priorities
- Single Docker Compose entrypoint.
- `.env` driven configuration.
- Clear migration path via Alembic.
- Minimal dependencies and typed Python code.
- First run provisions Miniflux automatically with curated starter feeds to reduce manual setup.
- Conservative runtime defaults: one API process, one scheduler, one inspector nginx worker, bounded clustering batches, and explicit env vars for tuning.
- Scheduler authority is isolated to the `worker` service. API workers never run scheduled jobs, and scheduler cycles use a Postgres advisory lock to avoid duplicate work if more than one worker container is started.
