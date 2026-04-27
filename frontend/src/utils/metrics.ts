import type { ParsedMetrics } from "../types";

const REQUIRED_KEYS: (keyof ParsedMetrics)[] = [
  "articles_ingested_total",
  "articles_deduplicated_total",
  "articles_malformed_total",
  "ingest_source_failures_total",
  "latest_articles_fetched",
  "latest_articles_stored",
  "latest_duplicate_articles_skipped",
  "latest_articles_malformed",
  "latest_failed_source_count",
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
    latest_articles_stored: null,
    latest_duplicate_articles_skipped: null,
    latest_articles_malformed: null,
    latest_failed_source_count: null,
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
