# Public Story Contract

`GET /api/clusters` and `GET /api/clusters/{cluster_id}` return the same public story object. The contract is additive: existing fields remain available, including `timeline`, `sources`, `score`, and `status`.

## Fields populated today

- `headline`, `summary`, `what_changed`, and `why_it_matters` come from the existing deterministic cluster enrichment pipeline.
- `timeline` and `timeline_events` contain the same event objects. Stored cluster timeline events are used first; if a cluster has no timeline rows yet, the API falls back to article publish timestamps and titles.
- `sources` lists associated articles, and `source_count` is computed from that list.
- `primary_image_url` and `thumbnail_urls` are extracted only from existing article `raw_payload` image fields or image enclosures. If no image URL exists, they return `null` and `[]`.
- `topic` uses the first available cluster keyword or entity. If none exists, it returns `"general"`.
- `last_updated`, `confidence_score`, and `is_developing` are derived from existing cluster timestamps, score, status, and source count.

## Safe defaults

Fields that need future pipeline support return safe non-fake defaults:

- `key_facts`: `[]`
- `region`: `null`
- `story_type`: `"general"`
- `is_breaking`: `false`
- `related_cluster_ids`: `[]`

## Future pipeline work

To make the consumer UI richer, add normalized ingestion or enrichment support for key facts, image metadata, topic/category classification, region detection, story type classification, breaking-news signals, and related-cluster linking. Those should be stored once they become first-class pipeline outputs rather than inferred as placeholder content in the API.
