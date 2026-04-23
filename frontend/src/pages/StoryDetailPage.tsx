import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { fetchClusterDetail } from "../api/client";
import type { StoryCluster } from "../types";
import { formatReadableTimestamp, formatTimestamp } from "../utils/format";
import { isRecentlyUpdated } from "../utils/homepage";

function formatEventTimestamp(value: string): string {
  return formatReadableTimestamp(value) ?? "";
}

function sourceLabel(sourceTitle: string, sourceUrl: string): string {
  const trimmedTitle = sourceTitle.trim();
  if (trimmedTitle) {
    return trimmedTitle;
  }

  try {
    return new URL(sourceUrl).hostname;
  } catch {
    return "";
  }
}

function sortEventsChronologically(cluster: StoryCluster) {
  const parseTime = (value: string) => {
    const time = Date.parse(value);
    return Number.isFinite(time) ? time : Number.POSITIVE_INFINITY;
  };

  return [...cluster.timeline].sort((left, right) => {
    const leftTime = parseTime(left.timestamp);
    const rightTime = parseTime(right.timestamp);
    return leftTime - rightTime;
  });
}

function sortSourcesByNewest(cluster: StoryCluster) {
  const parseTime = (value: string) => {
    const time = Date.parse(value);
    return Number.isFinite(time) ? time : Number.NEGATIVE_INFINITY;
  };

  return [...cluster.sources].sort((left, right) => {
    const leftTime = parseTime(left.published_at);
    const rightTime = parseTime(right.published_at);
    return rightTime - leftTime;
  });
}

export function StoryDetailPage() {
  const { clusterId = "" } = useParams();
  const [cluster, setCluster] = useState<StoryCluster | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!clusterId) {
      setLoading(false);
      setError("Missing story id.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await fetchClusterDetail(clusterId);
      setCluster(result);
    } catch (err) {
      setCluster(null);
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [clusterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const events = useMemo(() => (cluster ? sortEventsChronologically(cluster) : []), [cluster]);
  const sources = useMemo(() => (cluster ? sortSourcesByNewest(cluster) : []), [cluster]);
  const recentlyUpdated = cluster ? isRecentlyUpdated(cluster.last_updated) : false;
  const summaryText = cluster?.summary.trim() ?? "";
  const whatChangedText = cluster?.what_changed.trim() ?? "";
  const whyItMattersText = cluster?.why_it_matters.trim() ?? "";
  const sourceCount = cluster?.sources.length ?? 0;
  const firstSeenLabel = cluster ? formatTimestamp(cluster.first_seen) : "";
  const lastUpdatedLabel = cluster ? formatTimestamp(cluster.last_updated) : "";
  const firstSeenReadable = cluster ? formatReadableTimestamp(cluster.first_seen) : null;
  const lastUpdatedReadable = cluster ? formatReadableTimestamp(cluster.last_updated) : null;
  const storySections = [
    { title: "Summary", text: summaryText, className: "story-detail__section--lede" },
    { title: "What changed", text: whatChangedText },
    { title: "Why it matters", text: whyItMattersText }
  ].filter((section) => section.text.length > 0);

  return (
    <div className="public-page story-detail">
      <header className="story-detail__hero">
        <div className="story-detail__hero-copy">
          <p className="eyebrow">Live story detail</p>
          <h1>{cluster?.headline || "Story detail"}</h1>
          {cluster && (
            <div className="story-detail__meta">
              <span>
                {sourceCount} source{sourceCount === 1 ? "" : "s"}
              </span>
              {recentlyUpdated && <span className="story-detail__fresh">Recently updated</span>}
              {firstSeenReadable && <span>First seen {firstSeenReadable}</span>}
              {lastUpdatedReadable && <span>Last updated {lastUpdatedReadable}</span>}
            </div>
          )}
        </div>

        <div className="story-detail__actions">
          <Link className="secondary-button story-detail__back" to="/">
            Back to home
          </Link>
        </div>
      </header>

      <main className="story-detail__body">
        {loading && (
          <section className="state-panel" aria-busy="true">
            <p className="eyebrow">Loading</p>
            <h2>Fetching full story</h2>
            <p>Loading the structured cluster from /api/clusters/{clusterId}.</p>
          </section>
        )}

        {!loading && error && (
          <section className="state-panel state-panel--error" role="alert">
            <p className="eyebrow">Error</p>
            <h2>Could not load the story</h2>
            <p>{error}</p>
          </section>
        )}

        {!loading && !error && !cluster && (
          <section className="state-panel" role="status">
            <p className="eyebrow">Not found</p>
            <h2>Story unavailable</h2>
            <p>This story is not available through the public cluster API right now.</p>
          </section>
        )}

        {!loading && !error && cluster && (
          <>
            {storySections.map((section) => (
              <section key={section.title} className={`story-detail__section ${section.className ?? ""}`.trim()}>
                <h2>{section.title}</h2>
                <p>{section.text}</p>
              </section>
            ))}

            {events.length > 0 && (
              <section className="story-detail__section">
                <h2>Timeline</h2>
                <ol className="story-timeline">
                  {events.map((event, index) => {
                    const eventTime = formatEventTimestamp(event.timestamp);
                    const eventSource = event.source_url ? sourceLabel(event.source_title, event.source_url) : "";

                    return (
                      <li key={`${event.timestamp}-${index}`} className="story-timeline__item">
                        {eventTime && <div className="story-timeline__time">{eventTime}</div>}
                        <div className="story-timeline__body">
                          <p className="story-timeline__event">{event.event}</p>
                          {event.source_url && eventSource && (
                            <a href={event.source_url} target="_blank" rel="noreferrer" className="story-timeline__source">
                              {eventSource}
                            </a>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </section>
            )}

            {sources.length > 0 && (
              <section className="story-detail__section">
                <h2>Sources</h2>
                <ul className="story-sources">
                  {sources.map((source) => {
                    const sourceName = source.url ? sourceLabel(source.title, source.url) : "";
                    const publishedAt = formatReadableTimestamp(source.published_at);

                    return (
                      <li key={source.article_id} className="story-sources__item">
                        {source.publisher.trim() && <div className="story-sources__publisher">{source.publisher}</div>}
                        {source.url && sourceName && (
                          <a href={source.url} target="_blank" rel="noreferrer" className="story-sources__link">
                            {sourceName}
                          </a>
                        )}
                        {publishedAt && <div className="story-sources__published">{publishedAt}</div>}
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}

            <section className="story-detail__section story-detail__section--meta">
              <h2>Story details</h2>
              <dl className="story-detail__stats">
                <div>
                  <dt>Source count</dt>
                  <dd>{sourceCount}</dd>
                </div>
                <div>
                  <dt>First seen</dt>
                  <dd>{firstSeenReadable || firstSeenLabel}</dd>
                </div>
                <div>
                  <dt>Last updated</dt>
                  <dd>{lastUpdatedReadable || lastUpdatedLabel}</dd>
                </div>
              </dl>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
