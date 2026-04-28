import type { ParsedMetrics } from "../types";

const REQUIRED_KEYS: (keyof ParsedMetrics)[] = [
  "articles_ingested_total",
  "articles_deduplicated_total",
  "articles_malformed_total",
  "ingest_source_failures_total",
  "latest_articles_fetched",
  "configured_feed_count",
  "active_feed_count",
  "feeds_checked",
  "feeds_with_new_articles",
  "miniflux_entries_seen",
  "articles_fetched_raw",
  "latest_articles_stored",
  "articles_stored",
  "latest_duplicate_articles_skipped",
  "duplicate_articles_skipped",
  "latest_articles_malformed",
  "articles_rejected_quality",
  "articles_rejected_stale",
  "articles_rejected_service_finance",
  "latest_failed_source_count",
  "candidate_clusters_created",
  "clusters_promoted",
  "clusters_hidden",
  "clusters_created_total",
  "clusters_updated_total",
  "cluster_candidates_evaluated_total",
  "cluster_signal_rejected_total",
  "cluster_attach_decisions_total",
  "cluster_new_decisions_total",
  "cluster_low_confidence_new_total",
  "cluster_validation_rejected_total",
  "clusters_promoted_total",
  "clusters_hidden_total",
  "clusters_active_total",
  "cluster_promotion_attempts_total",
  "cluster_promotion_failures_total",
  "cluster_candidates_same_topic_total",
  "cluster_candidates_cross_topic_rejected_total",
  "cluster_entity_overlap_attach_total",
  "cluster_entity_conflict_rejected_total",
  "cluster_no_candidate_new_total",
  "cluster_topic_lane_attach_total",
  "cluster_topic_lane_new_total",
  "latest_candidate_clusters_created",
  "latest_clusters_updated",
  "latest_clusters_hidden",
  "latest_clusters_promoted",
  "latest_visible_clusters",
  "articles_pending_clustering",
  "summaries_pending",
  "active_sources",
  "last_ingest_time",
  "last_cluster_time"
];

export function parsePrometheusMetrics(raw: string): ParsedMetrics {
  const result: ParsedMetrics = {
    articles_ingested_total: null,
    articles_deduplicated_total: null,
    articles_malformed_total: null,
    ingest_source_failures_total: null,
    latest_articles_fetched: null,
    configured_feed_count: null,
    active_feed_count: null,
    feeds_checked: null,
    feeds_with_new_articles: null,
    miniflux_entries_seen: null,
    articles_fetched_raw: null,
    latest_articles_stored: null,
    articles_stored: null,
    latest_duplicate_articles_skipped: null,
    duplicate_articles_skipped: null,
    latest_articles_malformed: null,
    articles_rejected_quality: null,
    articles_rejected_stale: null,
    articles_rejected_service_finance: null,
    latest_failed_source_count: null,
    candidate_clusters_created: null,
    clusters_promoted: null,
    clusters_hidden: null,
    clusters_created_total: null,
    clusters_updated_total: null,
    cluster_candidates_evaluated_total: null,
    cluster_signal_rejected_total: null,
    cluster_attach_decisions_total: null,
    cluster_new_decisions_total: null,
    cluster_low_confidence_new_total: null,
    cluster_validation_rejected_total: null,
    clusters_promoted_total: null,
    clusters_hidden_total: null,
    clusters_active_total: null,
    cluster_promotion_attempts_total: null,
    cluster_promotion_failures_total: null,
    cluster_candidates_same_topic_total: null,
    cluster_candidates_cross_topic_rejected_total: null,
    cluster_entity_overlap_attach_total: null,
    cluster_entity_conflict_rejected_total: null,
    cluster_no_candidate_new_total: null,
    cluster_topic_lane_attach_total: null,
    cluster_topic_lane_new_total: null,
    latest_candidate_clusters_created: null,
    latest_clusters_updated: null,
    latest_clusters_hidden: null,
    latest_clusters_promoted: null,
    latest_visible_clusters: null,
    articles_pending_clustering: null,
    summaries_pending: null,
    active_sources: null,
    last_ingest_time: null,
    last_cluster_time: null
  };

  const lines = raw.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const [key, value] = trimmed.split(/\s+/, 2);
    if (!key || value === undefined) {
      continue;
    }

    if (REQUIRED_KEYS.includes(key as keyof ParsedMetrics)) {
      const parsed = Number(value);
      result[key as keyof ParsedMetrics] = Number.isFinite(parsed) ? parsed : null;
    }
  }

  return result;
}
