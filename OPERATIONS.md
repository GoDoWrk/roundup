# OPERATIONS

## Purpose
Fast checklist for confirming the Roundup pipeline is healthy and producing usable clusters.

## Start services
```bash
docker compose up --build
```

Expected order:
1. `db` healthy
2. `miniflux-db` healthy
3. `miniflux` healthy
4. `miniflux-bootstrap` completes
5. `migrate` completes
6. `api` and `worker` start
7. `inspector` starts

## Health checks
```bash
curl http://localhost:8000/health
curl http://localhost:8000/metrics
curl http://localhost:8000/api/clusters
curl http://localhost:8000/debug/clusters
```

Expected:
- `GET /health` returns `status=ok` or `status=degraded`
- `GET /api/clusters` shows only validated public clusters
- `GET /debug/clusters` includes rejected or hidden clusters with reasons

## Ingestion mode
Default mode should use live Miniflux:
- `DEMO_MODE=false`
- `MINIFLUX_URL=http://miniflux:8080`
- bootstrap writes `/miniflux-bootstrap/miniflux_api_key`

Demo mode is explicit only:
- set `DEMO_MODE=true`
- keep `SAMPLE_MINIFLUX_DATA_PATH` configured

## What to watch
Metrics that should move:
- `articles_ingested_total`
- `clusters_created_total`
- `clusters_updated_total`

Metrics that indicate ingestion trouble:
- `articles_malformed_total`
- `ingest_source_failures_total`

## Cluster lifecycle
Hidden clusters should still appear in `/debug/clusters` with:
- `source_count`
- `visibility_threshold`
- promotion fields

When a hidden cluster becomes valid, it should keep the same `cluster_id`, become `status=active`, and gain a non-null `promoted_at`.

Optional deterministic check:
```bash
docker compose exec api python scripts/demo_cluster_promotion.py
```

Expected phases:
- phase 1 hidden
- phase 2 hidden
- phase 3 promoted active

## UI check
Open `http://localhost:8080` and confirm:
- public cluster cards look coherent
- story detail shows timeline and sources
- inspector pages still render for debug use

## Common failures
- Worker exits at startup:
  - missing Miniflux token or config with `DEMO_MODE=false`
- `miniflux-bootstrap` exits:
  - invalid admin credentials
  - Miniflux not reachable
  - seed feed file missing or invalid
- `ingest_source_failures_total` rises:
  - Miniflux API unreachable or returning invalid data
- `articles_malformed_total` rises:
  - upstream feed entries are malformed and being skipped safely
- `/api/clusters` is empty but `/debug/clusters` is not:
  - clusters are failing validation and filtered from the public API as intended

