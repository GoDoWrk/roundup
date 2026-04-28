import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiErrorDetails, fetchClusterDetail, fetchDebugClusters, type ApiErrorDetails } from "../api/client";
import { QualityBadges } from "../components/QualityBadges";
import type { ClusterDebugItem, StoryCluster } from "../types";
import { formatScore, formatTimestamp } from "../utils/format";

export function ClusterDetailPage() {
  const { clusterId = "" } = useParams();

  const [cluster, setCluster] = useState<StoryCluster | null>(null);
  const [debugRows, setDebugRows] = useState<ClusterDebugItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorDetails, setErrorDetails] = useState<ApiErrorDetails | null>(null);
  const [debugErrorDetails, setDebugErrorDetails] = useState<ApiErrorDetails | null>(null);

  const load = useCallback(async () => {
    if (!clusterId) {
      return;
    }

    setLoading(true);
    setErrorDetails(null);
    setDebugErrorDetails(null);

    try {
      const [clusterData, debugData] = await Promise.allSettled([fetchClusterDetail(clusterId), fetchDebugClusters()]);
      if (clusterData.status === "fulfilled") {
        setCluster(clusterData.value);
      } else {
        setCluster(null);
        setErrorDetails(apiErrorDetails(clusterData.reason));
      }
      if (debugData.status === "fulfilled") {
        setDebugRows(debugData.value.items);
      } else {
        setDebugRows([]);
        setDebugErrorDetails(apiErrorDetails(debugData.reason));
      }
    } catch (err) {
      setErrorDetails(apiErrorDetails(err));
    } finally {
      setLoading(false);
    }
  }, [clusterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const debugItem = useMemo(() => debugRows.find((row) => row.cluster_id === clusterId) || null, [clusterId, debugRows]);
  const error = errorDetails?.message ?? null;
  const debugError = debugErrorDetails?.message ?? null;

  if (!clusterId) {
    return <p className="error">Missing cluster id.</p>;
  }

  return (
    <div>
      <section className="section">
        <div className="controls">
          <h2 style={{ margin: 0 }}>Cluster Detail</h2>
          <button onClick={() => void load()} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
          <Link to="/inspect">Back to list</Link>
        </div>

        {error && <p className="error">{error}</p>}
        {debugErrorDetails && (
          <p className="error">
            Debug cluster API unavailable: {debugErrorDetails.title}. {debugError}
          </p>
        )}
        {!error && loading && <p>Loading cluster...</p>}

        {!error && !loading && cluster && (
          <>
            <div className="meta">
              <div>
                <strong>cluster_id</strong>
                <div>{cluster.cluster_id}</div>
              </div>
              <div>
                <strong>status</strong>
                <div>{cluster.status}</div>
              </div>
              <div>
                <strong>topic</strong>
                <div>{cluster.topic || "(missing)"}</div>
              </div>
              <div>
                <strong>primary_topic</strong>
                <div>{cluster.primary_topic || "(missing)"}</div>
              </div>
              <div>
                <strong>subtopic</strong>
                <div>{cluster.subtopic || "(none)"}</div>
              </div>
              <div>
                <strong>geography</strong>
                <div>{cluster.geography || "(none)"}</div>
              </div>
              <div>
                <strong>event_type</strong>
                <div>{cluster.event_type || "(none)"}</div>
              </div>
              <div>
                <strong>score</strong>
                <div>{formatScore(cluster.score)}</div>
              </div>
              <div>
                <strong>first_seen</strong>
                <div>{formatTimestamp(cluster.first_seen)}</div>
              </div>
              <div>
                <strong>last_updated</strong>
                <div>{formatTimestamp(cluster.last_updated)}</div>
              </div>
              <div>
                <strong>source_count</strong>
                <div>{cluster.sources.length}</div>
              </div>
              {debugItem && (
                <>
                  <div>
                    <strong>visibility threshold</strong>
                    <div>{debugItem.visibility_threshold}</div>
                  </div>
                  <div>
                    <strong>promoted_at</strong>
                    <div>{debugItem.promoted_at ? formatTimestamp(debugItem.promoted_at) : "not promoted"}</div>
                  </div>
                </>
              )}
            </div>

            <div className="section">
              <h3>headline</h3>
              <p>{cluster.headline || "(blank)"}</p>
              <QualityBadges text={cluster.headline} />
            </div>

            <div className="section">
              <h3>summary</h3>
              <p>{cluster.summary || "(blank)"}</p>
              <QualityBadges text={cluster.summary} />
            </div>

            <div className="section">
              <h3>what_changed</h3>
              <p>{cluster.what_changed || "(blank)"}</p>
              <QualityBadges text={cluster.what_changed} />
            </div>

            <div className="section">
              <h3>why_it_matters</h3>
              <p>{cluster.why_it_matters || "(blank)"}</p>
              <QualityBadges text={cluster.why_it_matters} />
            </div>

            <div className="section">
              <h3>Timeline</h3>
              {cluster.timeline.length === 0 ? (
                <p>(no timeline events)</p>
              ) : (
                <ol>
                  {cluster.timeline.map((event, idx) => (
                    <li key={`${event.timestamp}-${idx}`}>
                      <strong>{formatTimestamp(event.timestamp)}</strong> - {event.event}
                      <div className="muted">
                        <a href={event.source_url} target="_blank" rel="noreferrer">
                          {event.source_title}
                        </a>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            <div className="section">
              <h3>Sources</h3>
              {cluster.sources.length === 0 ? (
                <p>(no sources)</p>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Publisher</th>
                      <th>Title</th>
                      <th>Published</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cluster.sources.map((source) => (
                      <tr key={source.article_id}>
                        <td>{source.publisher}</td>
                        <td>
                          <a href={source.url} target="_blank" rel="noreferrer">
                            {source.title}
                          </a>
                        </td>
                        <td>{formatTimestamp(source.published_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}

        {!error && !loading && !cluster && debugItem && (
          <div className="section">
            <h3>Not API-eligible</h3>
            <p>
              Cluster <code>{clusterId}</code> exists in debug output but is filtered from the main API.
            </p>
            <p>
              <strong>Status:</strong> {debugItem.status}
            </p>
            <p>
              <strong>Sources:</strong> {debugItem.source_count} / {debugItem.visibility_threshold}
            </p>
            <p>
              <strong>Promotion eligible:</strong> {debugItem.promotion_eligible ? "true" : "false"}
            </p>
            <p>
              <strong>Validation error:</strong> {debugItem.validation_error || "(none provided)"}
            </p>
            <pre>{JSON.stringify(debugItem.debug_explanation, null, 2)}</pre>
          </div>
        )}

        {!error && !loading && !cluster && !debugItem && (
          <p className="error">Cluster not found in API or debug endpoint.</p>
        )}
      </section>

      {debugItem && (
        <section className="section">
          <h3>Debug / Validation Information</h3>
          <p>
            <strong>debug status:</strong> {debugItem.status}
          </p>
          <p>
            <strong>debug score:</strong> {formatScore(debugItem.score)}
          </p>
          <p>
            <strong>debug topic:</strong> {debugItem.topic || "(missing)"}
          </p>
          <p>
            <strong>debug primary_topic:</strong> {debugItem.primary_topic || "(missing)"}
          </p>
          <p>
            <strong>debug subtopic:</strong> {debugItem.subtopic || "none"}
          </p>
          <p>
            <strong>debug geography:</strong> {debugItem.geography || "none"}
          </p>
          <p>
            <strong>debug event_type:</strong> {debugItem.event_type || "none"}
          </p>
          <p>
            <strong>debug key_entities:</strong>{" "}
            {debugItem.key_entities && debugItem.key_entities.length > 0 ? debugItem.key_entities.join(", ") : "none"}
          </p>
          <p>
            <strong>debug source_count:</strong> {debugItem.source_count}
          </p>
          <p>
            <strong>visibility threshold:</strong> {debugItem.visibility_threshold}
          </p>
          <p>
            <strong>promotion_eligible:</strong> {debugItem.promotion_eligible ? "true" : "false"}
          </p>
          <p>
            <strong>promoted_at:</strong> {debugItem.promoted_at ? formatTimestamp(debugItem.promoted_at) : "not promoted"}
          </p>
          <p>
            <strong>previous_status:</strong> {debugItem.previous_status || "none"}
          </p>
          <p>
            <strong>promotion_reason:</strong> {debugItem.promotion_reason || "none"}
          </p>
          <p>
            <strong>promotion_explanation:</strong> {debugItem.promotion_explanation || "none"}
          </p>
          <p>
            <strong>validation_error:</strong> {debugItem.validation_error || "none"}
          </p>
          <p>
            <strong>promotion blockers:</strong>{" "}
            {debugItem.promotion_blockers.length > 0 ? debugItem.promotion_blockers.join("; ") : "none"}
          </p>
          <p>
            <strong>score formula:</strong> {debugItem.debug_explanation.score_breakdown.score_formula}
          </p>
          <p>
            <strong>average score:</strong> {formatScore(debugItem.debug_explanation.score_breakdown.average_similarity_score)}
          </p>
          <p>
            <strong>average title similarity:</strong>{" "}
            {formatScore(debugItem.debug_explanation.score_breakdown.average_title_similarity)}
          </p>
          <p>
            <strong>average entity jaccard:</strong>{" "}
            {formatScore(debugItem.debug_explanation.score_breakdown.average_entity_jaccard)}
          </p>
          <p>
            <strong>average keyword jaccard:</strong>{" "}
            {formatScore(debugItem.debug_explanation.score_breakdown.average_keyword_jaccard)}
          </p>
          <p>
            <strong>average time proximity:</strong>{" "}
            {formatScore(debugItem.debug_explanation.score_breakdown.average_time_proximity)}
          </p>

          <h4>Grouping Explanation</h4>
          <p>{debugItem.debug_explanation.grouping_reason}</p>
          <pre>{JSON.stringify(debugItem.debug_explanation, null, 2)}</pre>
        </section>
      )}
    </div>
  );
}
