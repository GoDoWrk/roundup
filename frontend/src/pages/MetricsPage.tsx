import { useCallback, useEffect, useState } from "react";
import { apiErrorDetails, fetchMetricsText, type ApiErrorDetails } from "../api/client";
import type { ParsedMetrics } from "../types";
import { formatTimestamp } from "../utils/format";
import { parsePrometheusMetrics } from "../utils/metrics";

const REFRESH_INTERVAL_MS = 15000;

export function MetricsPage() {
  const [metrics, setMetrics] = useState<ParsedMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorDetails, setErrorDetails] = useState<ApiErrorDetails | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErrorDetails(null);

    try {
      const raw = await fetchMetricsText();
      setMetrics(parsePrometheusMetrics(raw));
    } catch (err) {
      setErrorDetails(apiErrorDetails(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) {
      return;
    }

    const handle = setInterval(() => {
      void load();
    }, REFRESH_INTERVAL_MS);

    return () => clearInterval(handle);
  }, [autoRefresh, load]);

  function valueDisplay(value: number | null): string {
    if (value === null) {
      return "(missing)";
    }
    return String(value);
  }

  const error = errorDetails?.message ?? null;

  const metricRows: Array<[string, number | null, "number" | "time", string]> = metrics
    ? [
        ["configured_feed_count", metrics.configured_feed_count, "number", "Feeds configured in Miniflux."],
        ["active_feed_count", metrics.active_feed_count, "number", "Feeds not disabled in Miniflux."],
        ["feeds_checked", metrics.feeds_checked, "number", "Active feeds queried this run."],
        ["feeds_with_new_articles", metrics.feeds_with_new_articles, "number", "Feeds with entries inside the lookback window."],
        ["miniflux_entries_seen", metrics.miniflux_entries_seen, "number", "Raw entries returned by Miniflux before filtering."],
        ["articles_fetched_raw", metrics.articles_fetched_raw, "number", "Recent per-feed candidates before global balancing."],
        ["latest_articles_fetched", metrics.latest_articles_fetched, "number", "Entries sent to ingestion after per-feed and category caps."],
        ["latest_articles_stored", metrics.latest_articles_stored, "number", "Articles inserted after quality filters and dedupe."],
        ["latest_duplicate_articles_skipped", metrics.latest_duplicate_articles_skipped, "number", "Candidates skipped because Roundup already had them."],
        ["latest_articles_malformed", metrics.latest_articles_malformed, "number", "Candidates skipped because required fields could not be parsed."],
        ["articles_rejected_quality", metrics.articles_rejected_quality, "number", "Candidates rejected by quality filters."],
        ["articles_rejected_stale", metrics.articles_rejected_stale, "number", "Quality rejections with stale-content reasons."],
        ["articles_rejected_service_finance", metrics.articles_rejected_service_finance, "number", "Quality rejections with service-finance reasons."],
        ["latest_failed_source_count", metrics.latest_failed_source_count, "number", "Ingestion source failures this run."],
        ["latest_candidate_clusters_created", metrics.latest_candidate_clusters_created, "number", "New candidate clusters created this run."],
        ["latest_clusters_updated", metrics.latest_clusters_updated, "number", "Clusters rebuilt this run."],
        ["latest_clusters_hidden", metrics.latest_clusters_hidden, "number", "Current hidden/debug-only clusters."],
        ["latest_clusters_promoted", metrics.latest_clusters_promoted, "number", "Clusters promoted to visible areas this run."],
        ["latest_visible_clusters", metrics.latest_visible_clusters, "number", "Current public/API-visible clusters."],
        ["articles_pending_clustering", metrics.articles_pending_clustering, "number", "Stored articles not attached to any cluster."],
        ["summaries_pending", metrics.summaries_pending, "number", "Clusters still carrying placeholder summary text."],
        ["active_sources", metrics.active_sources, "number", "Distinct publishers stored by Roundup."],
        ["articles_ingested_total", metrics.articles_ingested_total, "number", "Total inserted articles."],
        ["articles_deduplicated_total", metrics.articles_deduplicated_total, "number", "Total duplicate candidates skipped."],
        ["articles_malformed_total", metrics.articles_malformed_total, "number", "Total malformed candidates skipped."],
        ["ingest_source_failures_total", metrics.ingest_source_failures_total, "number", "Total source fetch failures."],
        ["clusters_created_total", metrics.clusters_created_total, "number", "Total clusters created."],
        ["clusters_updated_total", metrics.clusters_updated_total, "number", "Total cluster rebuilds."],
        ["cluster_candidates_evaluated_total", metrics.cluster_candidates_evaluated_total, "number", "Total candidate cluster comparisons."],
        ["cluster_signal_rejected_total", metrics.cluster_signal_rejected_total, "number", "Total candidate joins rejected by signal gates."],
        ["cluster_attach_decisions_total", metrics.cluster_attach_decisions_total, "number", "Total article-to-cluster attach decisions."],
        ["cluster_new_decisions_total", metrics.cluster_new_decisions_total, "number", "Total new-cluster decisions."],
        ["cluster_low_confidence_new_total", metrics.cluster_low_confidence_new_total, "number", "Total low-confidence new-cluster decisions."],
        ["cluster_validation_rejected_total", metrics.cluster_validation_rejected_total, "number", "Total cluster validation failures."],
        ["clusters_promoted_total", metrics.clusters_promoted_total, "number", "Total clusters promoted."],
        ["clusters_hidden_total", metrics.clusters_hidden_total, "number", "Current hidden cluster count."],
        ["clusters_active_total", metrics.clusters_active_total, "number", "Current active cluster count."],
        ["cluster_promotion_attempts_total", metrics.cluster_promotion_attempts_total, "number", "Total hidden-cluster promotion attempts."],
        ["cluster_promotion_failures_total", metrics.cluster_promotion_failures_total, "number", "Total promotion attempts that stayed hidden."],
        ["cluster_candidates_same_topic_total", metrics.cluster_candidates_same_topic_total, "number", "Same-primary-topic lane candidates selected for scoring."],
        ["cluster_candidates_cross_topic_rejected_total", metrics.cluster_candidates_cross_topic_rejected_total, "number", "Candidate comparisons rejected by primary topic mismatch."],
        ["cluster_entity_overlap_attach_total", metrics.cluster_entity_overlap_attach_total, "number", "Attachments supported by shared normalized entities."],
        ["cluster_entity_conflict_rejected_total", metrics.cluster_entity_conflict_rejected_total, "number", "Candidates rejected for conflicting primary entities."],
        ["cluster_no_candidate_new_total", metrics.cluster_no_candidate_new_total, "number", "New clusters created with no topic-lane candidates."],
        ["cluster_topic_lane_attach_total", metrics.cluster_topic_lane_attach_total, "number", "Attachments made after topic-lane candidate selection."],
        ["cluster_topic_lane_new_total", metrics.cluster_topic_lane_new_total, "number", "New clusters created after topic-lane candidate selection."],
        ["last_ingest_time", metrics.last_ingest_time, "time", "Last ingestion timestamp."],
        ["last_cluster_time", metrics.last_cluster_time, "time", "Last clustering timestamp."]
      ]
    : [];

  return (
    <section className="section">
      <div className="controls">
        <h2 style={{ margin: 0 }}>Basic Metrics</h2>
        <button onClick={() => void load()} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
        <label>
          <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
          Auto-refresh (15s)
        </label>
      </div>

      <p className="muted">Parsed from live `/metrics` Prometheus text output.</p>

      {errorDetails && (
        <p className="error">
          {errorDetails.title}: {error}
        </p>
      )}
      {!error && loading && <p>Loading metrics...</p>}

      {!error && metrics && (
        <table className="table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Value</th>
              <th>Meaning</th>
            </tr>
          </thead>
          <tbody>
            {metricRows.map(([name, value, type, description]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{type === "time" ? formatTimestamp(value) : valueDisplay(value)}</td>
                <td>{description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
