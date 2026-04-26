import { useCallback, useEffect, useState } from "react";
import { fetchMetricsText } from "../api/client";
import type { ParsedMetrics } from "../types";
import { formatTimestamp } from "../utils/format";
import { parsePrometheusMetrics } from "../utils/metrics";

const REFRESH_INTERVAL_MS = 15000;

export function MetricsPage() {
  const [metrics, setMetrics] = useState<ParsedMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const raw = await fetchMetricsText();
      setMetrics(parsePrometheusMetrics(raw));
    } catch (err) {
      setError((err as Error).message);
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

  const metricRows: Array<[string, number | null, "number" | "time"]> = metrics
    ? [
        ["latest_articles_fetched", metrics.latest_articles_fetched, "number"],
        ["latest_articles_stored", metrics.latest_articles_stored, "number"],
        ["latest_duplicate_articles_skipped", metrics.latest_duplicate_articles_skipped, "number"],
        ["latest_articles_malformed", metrics.latest_articles_malformed, "number"],
        ["latest_failed_source_count", metrics.latest_failed_source_count, "number"],
        ["latest_candidate_clusters_created", metrics.latest_candidate_clusters_created, "number"],
        ["latest_clusters_updated", metrics.latest_clusters_updated, "number"],
        ["latest_clusters_hidden", metrics.latest_clusters_hidden, "number"],
        ["latest_clusters_promoted", metrics.latest_clusters_promoted, "number"],
        ["latest_visible_clusters", metrics.latest_visible_clusters, "number"],
        ["articles_pending_clustering", metrics.articles_pending_clustering, "number"],
        ["summaries_pending", metrics.summaries_pending, "number"],
        ["active_sources", metrics.active_sources, "number"],
        ["articles_ingested_total", metrics.articles_ingested_total, "number"],
        ["articles_deduplicated_total", metrics.articles_deduplicated_total, "number"],
        ["articles_malformed_total", metrics.articles_malformed_total, "number"],
        ["ingest_source_failures_total", metrics.ingest_source_failures_total, "number"],
        ["clusters_created_total", metrics.clusters_created_total, "number"],
        ["clusters_updated_total", metrics.clusters_updated_total, "number"],
        ["cluster_candidates_evaluated_total", metrics.cluster_candidates_evaluated_total, "number"],
        ["cluster_signal_rejected_total", metrics.cluster_signal_rejected_total, "number"],
        ["cluster_attach_decisions_total", metrics.cluster_attach_decisions_total, "number"],
        ["cluster_new_decisions_total", metrics.cluster_new_decisions_total, "number"],
        ["cluster_low_confidence_new_total", metrics.cluster_low_confidence_new_total, "number"],
        ["cluster_validation_rejected_total", metrics.cluster_validation_rejected_total, "number"],
        ["clusters_promoted_total", metrics.clusters_promoted_total, "number"],
        ["clusters_hidden_total", metrics.clusters_hidden_total, "number"],
        ["clusters_active_total", metrics.clusters_active_total, "number"],
        ["cluster_promotion_attempts_total", metrics.cluster_promotion_attempts_total, "number"],
        ["cluster_promotion_failures_total", metrics.cluster_promotion_failures_total, "number"],
        ["last_ingest_time", metrics.last_ingest_time, "time"],
        ["last_cluster_time", metrics.last_cluster_time, "time"]
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

      {error && <p className="error">{error}</p>}
      {!error && loading && <p>Loading metrics...</p>}

      {!error && metrics && (
        <table className="table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            {metricRows.map(([name, value, type]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{type === "time" ? formatTimestamp(value) : valueDisplay(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
