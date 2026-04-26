import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchClusterList, fetchDebugClusters } from "../api/client";
import { QualityBadges } from "../components/QualityBadges";
import type { ClusterDebugItem, ClusterListResponse } from "../types";
import { toClusterListRows } from "../utils/clusterView";
import { formatScore, formatTimestamp } from "../utils/format";

export function ClusterListPage() {
  const [clusters, setClusters] = useState<ClusterListResponse | null>(null);
  const [debugClusters, setDebugClusters] = useState<ClusterDebugItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [clusterList, debug] = await Promise.all([
        fetchClusterList({ limit: 100, offset: 0 }),
        fetchDebugClusters()
      ]);
      setClusters(clusterList);
      setDebugClusters(debug.items);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const apiRows = useMemo(() => (clusters ? toClusterListRows(clusters) : []), [clusters]);
  const debugById = useMemo(
    () => new Map(debugClusters.map((item) => [item.cluster_id, item] as const)),
    [debugClusters]
  );
  const apiIds = new Set(apiRows.map((row) => row.clusterId));
  const invalidRows = debugClusters.filter((item) => item.validation_error || !apiIds.has(item.cluster_id));

  function isRecentlyPromoted(promotedAt: string | null): boolean {
    if (!promotedAt) {
      return false;
    }
    const parsed = Date.parse(promotedAt);
    if (Number.isNaN(parsed)) {
      return false;
    }
    return Date.now() - parsed <= 24 * 60 * 60 * 1000;
  }

  return (
    <div>
      <section className="section">
        <div className="controls">
          <h2 style={{ margin: 0 }}>Cluster List</h2>
          <button onClick={() => void load()} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        <p className="muted">Shows clusters currently eligible from the main API.</p>

        {error && <p className="error">{error}</p>}
        {!error && loading && <p>Loading clusters...</p>}
        {!error && !loading && apiRows.length === 0 && <p>No API-eligible clusters found.</p>}

        {!error && !loading && apiRows.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Headline</th>
                <th>Source Count</th>
                <th>First Seen</th>
                <th>Last Updated</th>
                <th>Score</th>
                <th>Promotion</th>
                <th>Summary Preview</th>
              </tr>
            </thead>
            <tbody>
              {apiRows.map((row) => {
                const debugRow = debugById.get(row.clusterId);
                return (
                  <tr key={row.clusterId}>
                    <td>
                      <Link to={`/inspect/clusters/${row.clusterId}`}>{row.headline}</Link>
                      <div className="muted">{row.topic || "general"}</div>
                      <div>
                        <QualityBadges text={row.headline} />
                      </div>
                    </td>
                    <td>{row.sourceCount}</td>
                    <td>{formatTimestamp(row.firstSeen)}</td>
                    <td>{formatTimestamp(row.lastUpdated)}</td>
                    <td>{formatScore(row.score)}</td>
                    <td>
                      {!debugRow?.promoted_at && debugRow?.promotion_blockers?.length ? (
                        <div className="quality-warn">
                          <span className="muted">blocked</span>
                          {debugRow.promotion_blockers.map((reason) => (
                            <code key={reason}>{reason}</code>
                          ))}
                        </div>
                      ) : null}
                      {!debugRow?.promoted_at && !debugRow?.promotion_blockers?.length && (
                        <span className="muted">no recent promotion</span>
                      )}
                      {debugRow?.promoted_at &&
                        (isRecentlyPromoted(debugRow.promoted_at) ? (
                          <span className="quality-ok">recently promoted</span>
                        ) : (
                          <span className="muted">promoted {formatTimestamp(debugRow.promoted_at)}</span>
                        ))}
                      {debugRow?.promotion_explanation && (
                        <div className="muted" style={{ marginTop: "0.35rem" }}>
                          {debugRow.promotion_explanation}
                        </div>
                      )}
                    </td>
                    <td>
                      <span>{row.summaryPreview}</span>
                      <div>
                        <QualityBadges text={row.summaryPreview} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <section className="section">
        <h3>Invalid/Debug Clusters</h3>
        <p className="muted">Clusters from `/debug/clusters` that are rejected or not present in `/api/clusters`.</p>

        {!error && !loading && invalidRows.length === 0 && <p>No invalid/debug-only clusters currently visible.</p>}

        {!error && !loading && invalidRows.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Cluster</th>
                <th>Status</th>
                <th>Score</th>
                <th>Sources / Threshold</th>
                <th>Promotion</th>
                <th>Validation Error</th>
                <th>Summary</th>
              </tr>
            </thead>
            <tbody>
              {invalidRows.map((row) => (
                <tr key={row.cluster_id}>
                  <td>
                    <Link to={`/clusters/${row.cluster_id}`}>{row.headline || row.cluster_id}</Link>
                    <div className="muted">{row.topic || "general"}</div>
                  </td>
                  <td>{row.status}</td>
                  <td>{formatScore(row.score)}</td>
                  <td>
                    {row.source_count} / {row.visibility_threshold}
                  </td>
                  <td>
                    {row.promoted_at ? (
                      isRecentlyPromoted(row.promoted_at) ? (
                        <span className="quality-ok">recently promoted</span>
                      ) : (
                        <span className="muted">promoted {formatTimestamp(row.promoted_at)}</span>
                      )
                    ) : (
                      <div className="quality-warn">
                        <span className="muted">{row.promotion_eligible ? "eligible, awaiting publish" : "not promoted"}</span>
                        {!row.promotion_eligible &&
                          row.promotion_blockers.map((reason) => <code key={reason}>{reason}</code>)}
                      </div>
                    )}
                  </td>
                  <td>{row.validation_error || "(none provided)"}</td>
                  <td>
                    <span>{row.summary || "(blank summary)"}</span>
                    <div>
                      <QualityBadges text={row.summary || ""} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
