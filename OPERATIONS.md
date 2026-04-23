# OPERATIONS

## Purpose
This runbook is a fast checklist to confirm the Roundup pipeline is healthy and producing usable clusters.

## 1) Start services
```bash
docker compose up --build
```

Expected startup order:
1. `db` healthy
2. `miniflux-db` healthy
3. `miniflux` healthy
4. `miniflux-bootstrap` completes
5. `migrate` completes
6. `api` and `worker` start
7. `inspector` starts

## 2) Confirm API health
```bash
curl http://localhost:8000/health
```
Expected:
- `status` is `ok` or `degraded`
- `db` is `ok`
- `miniflux_reachable` is `true`
- `miniflux_usable` is `true`

## 3) Confirm ingestion source
Default mode should be live Miniflux:
- `DEMO_MODE=false`
- `MINIFLUX_URL=http://miniflux:8080`
- bootstrap should write `/miniflux-bootstrap/miniflux_api_key` and set runtime token automatically

Demo mode is explicit only:
- set `DEMO_MODE=true`
- keep `SAMPLE_MINIFLUX_DATA_PATH` configured

## 4) Verify pipeline activity
Open metrics:
```bash
curl http://localhost:8000/metrics
```
Check these increase over time:
- `articles_ingested_total`
- `clusters_created_total`
- `clusters_updated_total`

Check for ingestion quality/resilience:
- `articles_malformed_total`
- `ingest_source_failures_total`

## 5) Verify cluster output
Main API:
```bash
curl http://localhost:8000/api/clusters
```
Debug API:
```bash
curl http://localhost:8000/debug/clusters
```

Expected:
- Main API shows only validated clusters.
- Debug API includes rejected clusters with validation/debug context.

## 6) Visual inspection UI
Open `http://localhost:8080`:
- Cluster list: check headline/summary quality and source counts.
- Cluster detail: check timeline and source ordering.
- Metrics page: confirm timestamps update.

## 7) Common failure patterns
- Worker exits at startup:
  - Missing Miniflux token/config with `DEMO_MODE=false`.
- API/worker never start and `miniflux-bootstrap` exits:
  - invalid `MINIFLUX_ADMIN_USERNAME`/`MINIFLUX_ADMIN_PASSWORD`
  - Miniflux service not reachable
  - feed seed file missing or invalid
- `ingest_source_failures_total` rising:
  - Miniflux API unreachable or invalid response.
- `articles_malformed_total` rising:
  - Upstream entries contain malformed fields and are being safely skipped.
- `/api/clusters` empty but `/debug/clusters` not empty:
  - Clusters are failing validation and being filtered as designed.
