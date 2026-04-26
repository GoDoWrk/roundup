import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { fetchClusterDetail } from "../api/client";
import { ClusterCard } from "../components/ClusterCard";
import { ImageWithFallback } from "../components/ImageWithFallback";
import { useFollowedStories } from "../context/FollowedStoriesContext";
import type { SourceReference, StoryCluster, TimelineEvent } from "../types";
import { formatReadableTimestamp, formatRelativeTime, formatTimestamp } from "../utils/format";
import { isRecentlyUpdated } from "../utils/homepage";

type TabKey = "timeline" | "facts" | "sources" | "related";

const INITIAL_TIMELINE_COUNT = 6;

const tabs: Array<{ id: TabKey; label: string }> = [
  { id: "timeline", label: "Timeline" },
  { id: "facts", label: "Key Facts" },
  { id: "sources", label: "Sources" },
  { id: "related", label: "Related" }
];

function asArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

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

function parseTime(value: string): number {
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : Number.NEGATIVE_INFINITY;
}

function sortEventsByNewest(cluster: StoryCluster) {
  const events = asArray(cluster.timeline_events?.length ? cluster.timeline_events : cluster.timeline);
  return [...events].sort((left, right) => parseTime(right.timestamp) - parseTime(left.timestamp));
}

function sortSourcesByNewest(cluster: StoryCluster) {
  return [...asArray(cluster.sources)].sort((left, right) => parseTime(right.published_at) - parseTime(left.published_at));
}

function sourceImageByUrl(sources: SourceReference[]) {
  const entries = sources
    .filter((source) => source.url?.trim() && source.image_url?.trim())
    .map((source) => [source.url, source.image_url] as const);
  return new Map(entries);
}

function StoryBrief({ cluster }: { cluster: StoryCluster }) {
  const sections = [
    { title: "Summary", text: cluster.summary?.trim() ?? "" },
    { title: "What changed", text: cluster.what_changed?.trim() ?? "" },
    { title: "Why it matters", text: cluster.why_it_matters?.trim() ?? "" }
  ].filter((section) => section.text.length > 0);

  if (sections.length === 0) {
    return null;
  }

  return (
    <section className="story-brief" aria-label="Story brief">
      {sections.map((section) => (
        <article key={section.title} className="story-brief__item">
          <h2>{section.title}</h2>
          <p>{section.text}</p>
        </article>
      ))}
    </section>
  );
}

function TimelineTab({
  cluster,
  events,
  visibleCount,
  onLoadOlder,
  thumbnailBySourceUrl
}: {
  cluster: StoryCluster;
  events: TimelineEvent[];
  visibleCount: number;
  onLoadOlder: () => void;
  thumbnailBySourceUrl: Map<string, string | null | undefined>;
}) {
  const visibleEvents = events.slice(0, visibleCount);
  const hasOlderEvents = events.length > visibleCount;

  return (
    <div className="story-tab-panel__content">
      <StoryBrief cluster={cluster} />

      {events.length === 0 ? (
        <section className="story-empty-state">
          <h2>No timeline updates yet</h2>
          <p>Roundup has not generated timeline events for this story yet.</p>
        </section>
      ) : (
        <section className="story-timeline-panel" aria-label="Timeline updates ordered newest to oldest">
          <ol className="story-timeline story-timeline--visual">
            {visibleEvents.map((event, index) => {
              const eventTime = formatEventTimestamp(event.timestamp);
              const eventSource = event.source_url ? sourceLabel(event.source_title, event.source_url) : "";
              const thumbnail = event.source_url ? thumbnailBySourceUrl.get(event.source_url) : null;

              return (
                <li key={`${event.timestamp}-${event.event}-${index}`} className="story-timeline__item">
                  <div className="story-timeline__marker-column" aria-hidden="true">
                    {index === 0 && <span className="story-timeline__latest-label">Latest</span>}
                    <span className={`story-timeline__dot${index === 0 ? " story-timeline__dot--latest" : ""}`} />
                  </div>
                  <div className="story-timeline__body">
                    {eventTime && <time className="story-timeline__time">{eventTime}</time>}
                    <p className="story-timeline__event">{event.event}</p>
                    {event.source_url && eventSource && (
                      <a href={event.source_url} target="_blank" rel="noreferrer" className="story-timeline__source">
                        {eventSource}
                      </a>
                    )}
                  </div>
                  {event.source_url && (
                    <ImageWithFallback
                      src={thumbnail}
                      label={eventSource || event.source_title}
                      className="story-timeline__thumbnail"
                      imageClassName="story-timeline__thumbnail-image"
                    />
                  )}
                </li>
              );
            })}
          </ol>

          {hasOlderEvents && (
            <button type="button" className="story-detail__load-older" onClick={onLoadOlder}>
              Load older updates
            </button>
          )}
        </section>
      )}
    </div>
  );
}

function KeyFactsTab({ facts }: { facts: string[] }) {
  if (facts.length === 0) {
    return (
      <section className="story-empty-state">
        <h2>No key facts available</h2>
        <p>Roundup has not extracted stable key facts from the current source set.</p>
      </section>
    );
  }

  return (
    <ul className="story-key-facts">
      {facts.map((fact, index) => (
        <li key={`${fact}-${index}`}>{fact}</li>
      ))}
    </ul>
  );
}

function SourcesTab({ sources }: { sources: SourceReference[] }) {
  if (sources.length === 0) {
    return (
      <section className="story-empty-state">
        <h2>No sources available</h2>
        <p>No public source articles are attached to this story right now.</p>
      </section>
    );
  }

  return (
    <ul className="story-sources story-sources--cards">
      {sources.map((source) => {
        const publishedAt = formatReadableTimestamp(source.published_at);
        const title = source.title?.trim() || sourceLabel("", source.url);

        return (
          <li key={source.article_id} className="story-sources__item">
            <ImageWithFallback
              src={source.image_url}
              label={source.publisher || title}
              className="story-sources__image"
              imageClassName="story-sources__image-element"
            />
            <div className="story-sources__copy">
              {source.publisher?.trim() && <div className="story-sources__publisher">{source.publisher}</div>}
              {source.url ? (
                <a href={source.url} target="_blank" rel="noreferrer" className="story-sources__link">
                  {title}
                </a>
              ) : (
                <span className="story-sources__link">{title}</span>
              )}
              {publishedAt && <time className="story-sources__published">{publishedAt}</time>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function RelatedTab({ loading, clusters }: { loading: boolean; clusters: StoryCluster[] }) {
  if (loading) {
    return (
      <section className="story-empty-state" aria-busy="true">
        <h2>Loading related stories</h2>
        <p>Checking public cluster links for this story.</p>
      </section>
    );
  }

  if (clusters.length === 0) {
    return (
      <section className="story-empty-state">
        <h2>No related stories yet</h2>
        <p>Roundup has not linked this story to other public clusters.</p>
      </section>
    );
  }

  return (
    <div className="story-related-grid">
      {clusters.map((related) => (
        <ClusterCard key={related.cluster_id} cluster={related} to={`/story/${related.cluster_id}`} variant="compact" />
      ))}
    </div>
  );
}

export function StoryDetailPage() {
  const { clusterId = "" } = useParams();
  const { isFollowed, toggleFollowed, markStoryViewed } = useFollowedStories();
  const [cluster, setCluster] = useState<StoryCluster | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("timeline");
  const [visibleTimelineCount, setVisibleTimelineCount] = useState(INITIAL_TIMELINE_COUNT);
  const [relatedClusters, setRelatedClusters] = useState<StoryCluster[]>([]);
  const [relatedLoading, setRelatedLoading] = useState(false);

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

  useEffect(() => {
    if (cluster && isFollowed(cluster.cluster_id)) {
      markStoryViewed(cluster);
    }
  }, [cluster, isFollowed, markStoryViewed]);

  useEffect(() => {
    setActiveTab("timeline");
    setVisibleTimelineCount(INITIAL_TIMELINE_COUNT);
  }, [cluster?.cluster_id]);

  const events = useMemo(() => (cluster ? sortEventsByNewest(cluster) : []), [cluster]);
  const sources = useMemo(() => (cluster ? sortSourcesByNewest(cluster) : []), [cluster]);
  const facts = useMemo(() => asArray(cluster?.key_facts).filter((fact) => fact.trim().length > 0), [cluster?.key_facts]);
  const relatedIds = useMemo(
    () => asArray(cluster?.related_cluster_ids).filter((id) => id.trim().length > 0),
    [cluster?.related_cluster_ids]
  );
  const thumbnailBySourceUrl = useMemo(() => sourceImageByUrl(sources), [sources]);

  useEffect(() => {
    let cancelled = false;

    async function loadRelated() {
      if (relatedIds.length === 0) {
        setRelatedClusters([]);
        setRelatedLoading(false);
        return;
      }

      setRelatedLoading(true);
      const results = await Promise.all(
        relatedIds.map(async (id) => {
          try {
            return await fetchClusterDetail(id);
          } catch {
            return null;
          }
        })
      );

      if (!cancelled) {
        setRelatedClusters(results.filter((item): item is StoryCluster => item !== null));
        setRelatedLoading(false);
      }
    }

    void loadRelated();
    return () => {
      cancelled = true;
    };
  }, [relatedIds]);

  const recentlyUpdated = cluster ? isRecentlyUpdated(cluster.last_updated) : false;
  const sourceCount = cluster?.source_count ?? cluster?.sources?.length ?? 0;
  const updateCount = events.length;
  const firstSeenReadable = cluster ? formatReadableTimestamp(cluster.first_seen) : null;
  const lastUpdatedReadable = cluster ? formatReadableTimestamp(cluster.last_updated) : null;
  const lastUpdatedFallback = cluster ? formatTimestamp(cluster.last_updated) : "";
  const relativeUpdated = cluster ? formatRelativeTime(cluster.last_updated) : "";
  const followed = cluster ? isFollowed(cluster.cluster_id) : false;

  return (
    <div className="public-page story-detail story-detail--tabbed">
      <header className="story-detail__header">
        <div className="story-detail__header-top">
          <Link className="story-detail__back-link" to="/">
            Back to all clusters
          </Link>
          <div className="story-detail__header-actions">
            <button
              type="button"
              className={`story-detail__follow-button${followed ? " story-detail__follow-button--saved" : ""}`}
              aria-label={followed ? "Unfollow story" : "Follow story"}
              aria-pressed={followed}
              disabled={!cluster}
              onClick={() => {
                if (cluster) {
                  toggleFollowed(cluster);
                }
              }}
            >
              {followed ? "Following" : "Follow"}
            </button>
            <button type="button" className="story-detail__overflow-button" aria-label="More story actions">
              ...
            </button>
          </div>
        </div>

        <div className="story-detail__headline-block">
          <h1>{cluster?.headline || "Story detail"}</h1>
          {cluster && (
            <div className="story-detail__meta" aria-label="Story metadata">
              <span>
                {updateCount} update{updateCount === 1 ? "" : "s"}
              </span>
              <span>
                {sourceCount} source{sourceCount === 1 ? "" : "s"}
              </span>
              {lastUpdatedReadable && <span>Last updated {relativeUpdated.startsWith("(") ? lastUpdatedReadable : relativeUpdated}</span>}
              {recentlyUpdated && <span className="story-detail__fresh">Recently updated</span>}
              {firstSeenReadable && <span>First seen {firstSeenReadable}</span>}
            </div>
          )}
        </div>
      </header>

      <main className="story-detail__body">
        {loading && (
          <section className="state-panel" aria-busy="true">
            <p className="eyebrow">Loading</p>
            <h2>Fetching full story</h2>
            <p>Loading the full story timeline, sources, and context.</p>
            <article className="story-card story-card--standard story-card--skeleton story-detail__loading-card" aria-hidden="true">
              <div className="story-card__image-frame" />
              <div className="story-card__content">
                <div className="story-card__eyebrow">
                  <span className="story-skeleton story-skeleton--pill" />
                  <span className="story-skeleton story-skeleton--line story-skeleton--tiny" />
                </div>
                <div className="story-skeleton story-skeleton--headline" />
                <div className="story-skeleton story-skeleton--line" />
                <div className="story-skeleton story-skeleton--line story-skeleton--short" />
              </div>
            </article>
          </section>
        )}

        {!loading && error && (
          <section className="state-panel state-panel--error" role="alert">
            <p className="eyebrow">Error</p>
            <h2>Could not load the story</h2>
            <p>{error}</p>
            <button type="button" className="secondary-action" onClick={() => void load()}>
              Retry loading story
            </button>
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
          <section className="story-tabs-card">
            <div className="story-tabs" role="tablist" aria-label="Story sections">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  id={`story-tab-${tab.id}`}
                  aria-selected={activeTab === tab.id}
                  aria-controls={`story-panel-${tab.id}`}
                  className={`story-tabs__button${activeTab === tab.id ? " story-tabs__button--active" : ""}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div
              role="tabpanel"
              id={`story-panel-${activeTab}`}
              aria-labelledby={`story-tab-${activeTab}`}
              className="story-tab-panel"
            >
              {activeTab === "timeline" && (
                <TimelineTab
                  cluster={cluster}
                  events={events}
                  visibleCount={visibleTimelineCount}
                  onLoadOlder={() => setVisibleTimelineCount((count) => count + INITIAL_TIMELINE_COUNT)}
                  thumbnailBySourceUrl={thumbnailBySourceUrl}
                />
              )}
              {activeTab === "facts" && <KeyFactsTab facts={facts} />}
              {activeTab === "sources" && <SourcesTab sources={sources} />}
              {activeTab === "related" && <RelatedTab loading={relatedLoading} clusters={relatedClusters} />}
            </div>

            {(lastUpdatedReadable || lastUpdatedFallback) && (
              <footer className="story-detail__api-note">
                <span>Updated {lastUpdatedReadable || lastUpdatedFallback}</span>
              </footer>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
