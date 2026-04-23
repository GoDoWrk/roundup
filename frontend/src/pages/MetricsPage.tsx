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
            <tr>
              <td>articles_ingested_total</td>
              <td>{valueDisplay(metrics.articles_ingested_total)}</td>
            </tr>
            <tr>
              <td>articles_deduplicated_total</td>
              <td>{valueDisplay(metrics.articles_deduplicated_total)}</td>
            </tr>
            <tr>
              <td>clusters_created_total</td>
              <td>{valueDisplay(metrics.clusters_created_total)}</td>
            </tr>
            <tr>
              <td>clusters_updated_total</td>
              <td>{valueDisplay(metrics.clusters_updated_total)}</td>
            </tr>
            <tr>
              <td>clusters_promoted_total</td>
              <td>{valueDisplay(metrics.clusters_promoted_total)}</td>
            </tr>
            <tr>
              <td>clusters_hidden_total</td>
              <td>{valueDisplay(metrics.clusters_hidden_total)}</td>
            </tr>
            <tr>
              <td>clusters_active_total</td>
              <td>{valueDisplay(metrics.clusters_active_total)}</td>
            </tr>
            <tr>
              <td>cluster_promotion_attempts_total</td>
              <td>{valueDisplay(metrics.cluster_promotion_attempts_total)}</td>
            </tr>
            <tr>
              <td>cluster_promotion_failures_total</td>
              <td>{valueDisplay(metrics.cluster_promotion_failures_total)}</td>
            </tr>
            <tr>
              <td>last_ingest_time</td>
              <td>{formatTimestamp(metrics.last_ingest_time)}</td>
            </tr>
            <tr>
              <td>last_cluster_time</td>
              <td>{formatTimestamp(metrics.last_cluster_time)}</td>
            </tr>
          </tbody>
        </table>
      )}
    </section>
  );
}
