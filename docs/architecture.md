# Roundup Architecture Note

## Why this design
Roundup v1 is intentionally backend-first and deterministic. The objective is a boring, inspectable pipeline that can ingest articles from Miniflux, store and deduplicate them, cluster related coverage, and expose validated story objects through an API.

## Major components
- **FastAPI API service**: exposes health, metrics, public cluster/article APIs, and debug visibility.
- **Worker service**: runs the interval scheduler and executes ingestion + clustering pipeline.
- **Postgres**: source of truth for articles, clusters, timeline events, and persistent pipeline counters.

## Pipeline shape
1. Pull entries from Miniflux (`/v1/entries`).
2. Normalize article text/metadata into deterministic features.
3. Deduplicate on stable `dedupe_hash`.
4. Cluster unclustered articles using deterministic weighted heuristics.
5. Enrich strict cluster fields with deterministic templates.
6. Validate required cluster text fields and mark invalid clusters.
7. Expose only valid clusters in `/api/clusters`, with invalid state visible in `/debug/clusters`.

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
