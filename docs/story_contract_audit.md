# Story Contract Audit: Backend + Frontend vs Target Roundup Consumer UI

Date: 2026-04-25

Scope audited:
- backend models
- database migrations
- API schemas/serializers
- clustering pipeline
- summarization/enrichment pipeline
- article ingestion models
- frontend API client
- homepage + story detail components
- backend/frontend tests

## 1) Current fields available from cluster/story APIs

Current public cluster APIs:
- `GET /api/clusters`
- `GET /api/clusters/{cluster_id}`

Current `StoryCluster` response contract (as implemented):
- `cluster_id`
- `headline`
- `topic`
- `summary`
- `what_changed`
- `why_it_matters`
- `timeline` (array of `{timestamp, event, source_url, source_title}`)
- `sources` (array of `{article_id, title, url, publisher, published_at}`)
- `first_seen`
- `last_updated`
- `score`
- `status` (`emerging|active|stale`)

Notes:
- `source_count` is not emitted explicitly; frontend computes from `sources.length`.
- `timeline_events` naming does not exist in API; the field is currently named `timeline`.
- `confidence_score` naming does not exist in API; closest current field is `score`.

## 2) Missing fields required by the mockup

Target fields requested:
- headline ✅ present
- summary ✅ present
- what_changed ✅ present
- why_it_matters ✅ present
- key_facts ❌ missing
- timeline_events ❌ missing (functional equivalent exists as `timeline`)
- sources ✅ present
- source_count ❌ missing (derivable)
- primary_image_url ❌ missing
- thumbnail_urls ❌ missing
- topic ✅ present
- region ❌ missing
- story_type ❌ missing
- last_updated ✅ present
- is_developing ❌ missing
- is_breaking ❌ missing
- confidence_score ❌ missing (functional equivalent exists as `score`)
- related_cluster_ids ❌ missing

## 3) Missing field strategy: derived, stored, or computed at response time

| Missing field | Recommended strategy | Why |
|---|---|---|
| `key_facts` | **Derived + stored** (cluster-level JSON/text list) | Facts should be stable across clients and testable; deriving once during cluster rebuild avoids repeated NLP work per request. |
| `timeline_events` | **Computed at response time (alias)** | No schema change needed: map existing `timeline` to `timeline_events` in serializer/versioned response contract. |
| `source_count` | **Computed at response time** | Deterministic from `len(sources)`; avoid denormalization. |
| `primary_image_url` | **Derived + stored** (article + cluster) | Needs ingestion/extraction and deterministic selection per cluster. |
| `thumbnail_urls` | **Derived + stored** (article + cluster) | Similar to primary image; used for cards/details and should not be recomputed per request. |
| `region` | **Derived + stored** | Region classification should be consistent across runs and reusable for filtering/ranking. |
| `story_type` | **Derived + stored** | Editorial taxonomy should be stable for UI chips/filtering and analytics. |
| `is_developing` | **Computed at response time** (from `status`/freshness) | Can be derived from existing `status == emerging` (or a refined rule later). |
| `is_breaking` | **Derived + stored** (with fallback computed rule) | Breaking is a product-level signal likely requiring rules/ML and explicit auditability. |
| `confidence_score` | **Computed at response time (alias)** | Map from current `score` initially; preserve room for future independent confidence model. |
| `related_cluster_ids` | **Derived + stored** (or cached computation) | Requires cross-cluster similarity query; expensive per request if not cached. |

## 4) Specific backend files that need changes (for follow-up implementation)

### Public API contract + serialization
- `app/schemas/cluster.py`
  - Add new response fields to `StoryCluster` (or create a v2 schema).
  - Optionally preserve backward compatibility by keeping `timeline`/`score` while adding `timeline_events`/`confidence_score`.
- `app/services/serialization.py`
  - Populate new fields (`source_count`, aliases, booleans, any stored metadata fields).
  - Normalize naming to the target contract.
- `app/api/routes/clusters.py`
  - If contract versioning is introduced, wire v2 response model or query flag.

### Data model + migrations (future PRs, not this audit)
- `app/db/models.py`
  - Cluster model needs stored metadata fields for: `key_facts`, `region`, `story_type`, `is_breaking`, `related_cluster_ids`, image fields.
  - Article model needs image metadata extracted at ingest.
- `alembic/versions/*`
  - New migration(s) to add required persisted fields.

### Pipeline generation points
- `app/services/enrichment.py`
  - Add builders/extractors for `key_facts`, `region`, `story_type`, potential `is_breaking` heuristic seed.
- `app/services/clustering.py`
  - During `_rebuild_cluster`, compute/store new enrichment outputs.
  - Add logic for related cluster linkage generation (or write hooks).
- `app/services/ingestion.py`
  - Extend normalized article ingestion to capture image candidates/metadata if available.
- `app/services/normalizer.py`
  - Add parsing for image metadata from source payload where possible.

### Backend tests to update/add
- `tests/test_api_routes.py`
  - Contract tests for new fields and aliases.
- `tests/test_clustering.py`
  - Validate cluster rebuild sets stored enrichment fields.
- `tests/test_pipeline.py`
  - End-to-end checks for ingest -> cluster -> API with new fields.
- (Potential) add dedicated tests for serializer mapping, e.g. `tests/test_serialization.py`.

## 5) Specific frontend files that need changes (for follow-up implementation)

### Contract typing + client
- `frontend/src/types.ts`
  - Add target fields to `StoryCluster` interface.
  - Handle possible transitional fields (`timeline` vs `timeline_events`, `score` vs `confidence_score`).
- `frontend/src/api/client.ts`
  - Add response normalization adapter if backend rolls out fields incrementally.

### Homepage components
- `frontend/src/components/ClusterCard.tsx`
  - Use `source_count` when available.
  - Add UI support for topic/region/story type/chips and thumbnail/primary image usage.
  - Replace raw `score` display with `confidence_score` if target UI expects that label.
- `frontend/src/pages/HomePage.tsx`
  - Read/sort/filter by new metadata fields if required by mockup.
- `frontend/src/utils/homepage.ts`
  - Sorting/filtering helpers for new fields (`is_breaking`, `is_developing`, `region`, `story_type`).

### Story detail components
- `frontend/src/pages/StoryDetailPage.tsx`
  - Consume `timeline_events`, `key_facts`, `related_cluster_ids`, image fields, confidence/developing/breaking flags.

### Frontend tests to update/add
- `frontend/src/pages/HomePage.test.tsx`
- `frontend/src/pages/StoryDetailPage.test.tsx`
- `frontend/src/components/ClusterCard.test.tsx`
- `frontend/src/utils/homepage.test.ts`

Update fixtures/mocks in these tests to include the new contract fields and verify rendering behavior.

## 6) Recommended PR sequence

1. **PR 1: API contract surface (non-breaking adapter)**
   - Add target response fields at serializer/schema layer only where derivable now:
     - `source_count`, `timeline_events` alias, `confidence_score` alias, `is_developing` (derived).
   - Keep existing fields for compatibility.
   - Add/adjust backend API tests.

2. **PR 2: Frontend contract adoption (compat mode)**
   - Update TS types + client adapter + homepage/story detail usage for new field names.
   - Keep fallback logic for legacy fields.
   - Update frontend tests.

3. **PR 3: Persisted enrichment phase 1**
   - Add DB fields + migration for `key_facts`, `region`, `story_type`, image metadata.
   - Extend enrichment/clustering/ingestion to populate them.
   - Add backend tests.

4. **PR 4: Breaking/developing/confidence semantics hardening**
   - Introduce explicit `is_breaking` logic and confidence calibration if distinct from `score`.
   - Tighten validation and regression tests.

5. **PR 5: Related clusters**
   - Implement related-cluster derivation/caching and expose `related_cluster_ids`.
   - Add API + UI integration tests.

6. **PR 6: Cleanup and contract deprecation**
   - Deprecate legacy aliases (`timeline`, `score`) once all clients are migrated.

## Additional observations from current codebase

- Enrichment currently only generates: `headline`, `summary`, `what_changed`, `why_it_matters`, `timeline` and `status`; no key facts, region, story type, or image outputs yet.
- Cluster data quality validation currently checks only text completeness/quality and does not validate any of the target metadata fields.
- Frontend currently renders text-first story cards/details and has no image or related-story surfaces.



## PR 1 implementation checklist (directly actionable)

Scope: ship only response-contract additions that do **not** require schema changes.

- Backend
  - `app/schemas/cluster.py`: add `source_count`, `timeline_events`, `confidence_score`, `is_developing` to `StoryCluster`.
  - `app/services/serialization.py`:
    - `source_count = len(sources)`
    - `timeline_events = timeline` (same payload shape)
    - `confidence_score = cluster.score`
    - `is_developing = (cluster.status == "emerging")`
- Frontend
  - `frontend/src/types.ts`: add the same fields (keep legacy `timeline` and `score` during transition).
  - `frontend/src/api/client.ts`: add a normalizer so either legacy or new fields can be consumed safely.
  - `frontend/src/pages/HomePage.tsx`, `frontend/src/components/ClusterCard.tsx`, `frontend/src/pages/StoryDetailPage.tsx`: read `source_count`/`confidence_score` with fallback to legacy fields.
- Tests
  - Backend: update `tests/test_api_routes.py` assertions for new fields.
  - Frontend: update mock fixtures in `HomePage.test.tsx`, `StoryDetailPage.test.tsx`, and `ClusterCard.test.tsx`.

Out of scope for PR 1: `key_facts`, images, `region`, `story_type`, `is_breaking`, `related_cluster_ids` (these require persistence/enrichment work).
