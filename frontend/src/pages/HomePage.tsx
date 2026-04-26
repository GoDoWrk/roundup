import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchClusterList, fetchMetricsText } from "../api/client";
import { ClusterCard } from "../components/ClusterCard";
import { FeedControls } from "../components/FeedControls";
import type { ParsedMetrics, StoryCluster } from "../types";
import { formatReadableTimestamp, formatRelativeTime } from "../utils/format";
import {
  collectTopics,
  getChangedClusterIds,
  getFilteredClusters,
  selectHomepageSections
} from "../utils/homepage";
import { parsePrometheusMetrics } from "../utils/metrics";

const PAGE_LIMIT = 20;
const REFRESH_INTERVAL_MS = 30_000;

type SortMode = "top" | "latest";

function SkeletonCard({ variant = "standard" }: { variant?: "standard" | "featured" | "compact" }) {
  return (
    <article className={`story-card story-card--${variant} story-card--skeleton`} aria-hidden="true">
      <div className="story-card__image-frame" />
      <div className="story-card__content">
        <div className="story-card__eyebrow">
          <span className="story-skeleton story-skeleton--line story-skeleton--tiny" />
          <span className="story-skeleton story-skeleton--pill" />
        </div>
        <div className="story-skeleton story-skeleton--headline" />
        <div className="story-skeleton story-skeleton--line" />
        <div className="story-skeleton story-skeleton--line story-skeleton--short" />
        <div className="story-card__footer">
          <span className="story-skeleton story-skeleton--line story-skeleton--tiny" />
          <span className="story-skeleton story-skeleton--line story-skeleton--tiny" />
        </div>
      </div>
    </article>
  );
}

function SectionHeader({ id, title, detail }: { id: string; title: string; detail?: string }) {
  return (
    <div className="dashboard-section__header">
      <h2 id={id}>{title}</h2>
      {detail && <p>{detail}</p>}
    </div>
  );
}

function formatStatusTimestamp(value: string | number | null, referenceTime: number): string | null {
  const readable = formatReadableTimestamp(value);
  if (!readable) {
    return null;
  }

  return `${formatRelativeTime(value, referenceTime)} (${readable})`;
}

function getLatestClusterTimestamp(clusters: StoryCluster[]): number | null {
  let latest: number | null = null;

  for (const cluster of clusters) {
    const timestamp = Date.parse(cluster.last_updated);
    if (Number.isFinite(timestamp) && (latest === null || timestamp > latest)) {
      latest = timestamp;
    }
  }

  return latest;
}

export function HomePage() {
  const [clusters, setClusters] = useState<StoryCluster[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastLoadedAt, setLastLoadedAt] = useState<number | null>(null);
  const [metrics, setMetrics] = useState<ParsedMetrics | null>(null);
  const [clockNow, setClockNow] = useState(() => Date.now());
  const [sortMode, setSortMode] = useState<SortMode>("top");
  const [topicFilter, setTopicFilter] = useState("all");
  const [showAllClusters, setShowAllClusters] = useState(false);
  const [highlightedClusterIds, setHighlightedClusterIds] = useState<Set<string>>(new Set());
  const [updatedSinceLastRefresh, setUpdatedSinceLastRefresh] = useState(0);
  const requestInFlight = useRef(false);
  const previousSnapshotRef = useRef<Map<string, string>>(new Map());

  const load = useCallback(async (background = false) => {
    if (requestInFlight.current) {
      return;
    }

    requestInFlight.current = true;
    if (background) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const [response, metricsText] = await Promise.all([
        fetchClusterList({ limit: PAGE_LIMIT, offset: 0 }),
        fetchMetricsText().catch(() => null)
      ]);
      const changedIds = getChangedClusterIds(previousSnapshotRef.current, response.items);
      const currentSnapshot = new Map<string, string>();

      for (const cluster of response.items) {
        currentSnapshot.set(cluster.cluster_id, cluster.last_updated);
      }

      previousSnapshotRef.current = currentSnapshot;
      setClusters(response.items);
      setTotal(response.total);
      setLastLoadedAt(Date.now());
      setClockNow(Date.now());
      setMetrics(metricsText ? parsePrometheusMetrics(metricsText) : null);
      setHighlightedClusterIds(changedIds);
      setUpdatedSinceLastRefresh(changedIds.size);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
      if (!background) {
        setClusters([]);
        setTotal(0);
        setHighlightedClusterIds(new Set());
        setUpdatedSinceLastRefresh(0);
      }
    } finally {
      requestInFlight.current = false;
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  useEffect(() => {
    const handle = window.setInterval(() => {
      void load(true);
    }, REFRESH_INTERVAL_MS);

    return () => window.clearInterval(handle);
  }, [load]);

  useEffect(() => {
    const handle = window.setInterval(() => {
      setClockNow(Date.now());
    }, 1000);

    return () => window.clearInterval(handle);
  }, []);

  const topics = useMemo(() => collectTopics(clusters), [clusters]);

  useEffect(() => {
    if (topicFilter !== "all" && !topics.includes(topicFilter)) {
      setTopicFilter("all");
    }
  }, [topicFilter, topics]);

  const filteredClusters = useMemo(() => getFilteredClusters(clusters, topicFilter), [clusters, topicFilter]);
  const sections = useMemo(() => selectHomepageSections(filteredClusters, sortMode), [filteredClusters, sortMode]);

  const visibleCount = sections.allClusters.length;
  const hasStories = visibleCount > 0;
  const hasLoadedData = clusters.length > 0 || total > 0 || lastLoadedAt !== null;
  const topicFilterLabel = topicFilter === "all" ? "All topics" : topicFilter;
  const liveCountLabel =
    visibleCount === 0
      ? hasLoadedData && topicFilter !== "all"
        ? `No stories in ${topicFilterLabel}`
        : "No live stories"
      : total > visibleCount && topicFilter === "all"
        ? `Showing ${visibleCount} of ${total} clusters`
        : `${visibleCount} live ${visibleCount === 1 ? "cluster" : "clusters"}`;
  const sortLabel = sortMode === "latest" ? "Latest Updates" : "Top / Most Important";
  const pageRefreshLabel = lastLoadedAt ? formatStatusTimestamp(lastLoadedAt, clockNow) : "Waiting for live data";
  const lastIngestionLabel = metrics?.last_ingest_time
    ? formatStatusTimestamp(metrics.last_ingest_time, clockNow)
    : null;
  const lastClusterUpdateLabel = metrics?.last_cluster_time
    ? formatStatusTimestamp(metrics.last_cluster_time, clockNow)
    : formatStatusTimestamp(getLatestClusterTimestamp(clusters), clockNow);
  const nextRefreshLabel = lastLoadedAt
    ? refreshing
      ? "Refreshing now"
      : `in ${Math.max(1, Math.ceil((lastLoadedAt + REFRESH_INTERVAL_MS - clockNow) / 1000))}s`
    : "after first load";

  return (
    <div className="public-page public-page--dashboard">
      <header className="public-hero">
        <div className="public-hero__copy">
          <p className="eyebrow">Updated live</p>
          <h1>Top Stories</h1>
          <p>Current Roundup clusters organized into a fast, consumer-ready news dashboard.</p>
        </div>

        <div className="public-hero__actions">
          <button type="button" className="primary-button" onClick={() => void load(true)} disabled={loading || refreshing}>
            {loading || refreshing ? "Updating..." : "Refresh"}
          </button>
        </div>

        <div className="public-hero__meta" aria-live="polite">
          <span>
            <strong>Live feed</strong>
            {liveCountLabel}
          </span>
          <span>
            <strong>Page refreshed</strong>
            {pageRefreshLabel}
          </span>
          {lastIngestionLabel && (
            <span>
              <strong>Last ingestion</strong>
              {lastIngestionLabel}
            </span>
          )}
          {lastClusterUpdateLabel && (
            <span>
              <strong>Last cluster update</strong>
              {lastClusterUpdateLabel}
            </span>
          )}
          <span>
            <strong>Next auto-refresh</strong>
            {nextRefreshLabel}
          </span>
          <span>
            <strong>Sort</strong>
            {sortLabel}
          </span>
          <span>
            <strong>Topic</strong>
            {topicFilterLabel}
          </span>
          {updatedSinceLastRefresh > 0 && (
            <span className="public-hero__accent">{updatedSinceLastRefresh} updated since last refresh</span>
          )}
        </div>
      </header>

      <FeedControls
        sortMode={sortMode}
        topics={topics}
        topicFilter={topicFilter}
        onSortModeChange={setSortMode}
        onTopicFilterChange={setTopicFilter}
      />

      <main className="public-feed">
        {error && hasStories && (
          <div className="banner banner--warning" role="status">
            Live refresh failed: {error}. Showing the last successful results.
            <button type="button" className="banner__action" onClick={() => void load(true)}>
              Retry
            </button>
          </div>
        )}

        {refreshing && hasStories && (
          <div className="banner banner--loading" role="status" aria-busy="true">
            Refreshing live stories...
          </div>
        )}

        {loading && !hasLoadedData && (
          <section className="state-panel state-panel--loading" aria-busy="true">
            <p className="eyebrow">Loading live feed</p>
            <h2>Checking Roundup for current stories</h2>
            <p>Pulling the latest cluster data and preparing the dashboard.</p>
            <div className="top-stories-layout top-stories-layout--skeleton" aria-hidden="true">
              <SkeletonCard variant="featured" />
              <div className="supporting-story-stack">
                {Array.from({ length: 3 }).map((_, index) => (
                  <SkeletonCard key={index} variant="compact" />
                ))}
              </div>
            </div>
          </section>
        )}

        {!loading && !error && !hasStories && hasLoadedData && topicFilter !== "all" && (
          <section className="state-panel">
            <p className="eyebrow">Filtered view</p>
            <h2>No stories in {topicFilter}</h2>
            <p>Try a different topic or return to all topics to keep scanning the live feed.</p>
            <button className="secondary-action" onClick={() => setTopicFilter("all")} type="button">
              Show all topics
            </button>
          </section>
        )}

        {!loading && !error && !hasStories && hasLoadedData && topicFilter === "all" && (
          <section className="state-panel">
            <p className="eyebrow">Nothing to show yet</p>
            <h2>No live stories available</h2>
            <p>The feed will populate automatically once live clusters are available from the backend.</p>
          </section>
        )}

        {!loading && !hasStories && error && (
          <section className="state-panel state-panel--error" role="alert">
            <p className="eyebrow">Feed error</p>
            <h2>Could not load live stories</h2>
            <p>{error}</p>
            <button className="secondary-action" onClick={() => void load(false)} type="button">
              Retry loading stories
            </button>
          </section>
        )}

        {hasStories && sections.leadStory && (
          <>
            <section className="dashboard-section" aria-labelledby="top-stories-heading">
              <SectionHeader id="top-stories-heading" title="Top Stories" detail="Highest-ranked clusters from the live API." />
              <div className="top-stories-layout">
                <ClusterCard
                  cluster={sections.leadStory}
                  to={`/story/${sections.leadStory.cluster_id}`}
                  highlighted={highlightedClusterIds.has(sections.leadStory.cluster_id)}
                  variant="featured"
                />
                {sections.supportingStories.length > 0 && (
                  <div className="supporting-story-stack" aria-label="Supporting top stories">
                    {sections.supportingStories.map((cluster) => (
                      <ClusterCard
                        key={cluster.cluster_id}
                        cluster={cluster}
                        to={`/story/${cluster.cluster_id}`}
                        highlighted={highlightedClusterIds.has(cluster.cluster_id)}
                        variant="compact"
                      />
                    ))}
                  </div>
                )}
              </div>
            </section>

            {sections.developingStories.length > 0 && (
              <section className="dashboard-section" aria-labelledby="developing-stories-heading">
                <SectionHeader
                  id="developing-stories-heading"
                  title="Developing Stories"
                  detail="Recently updated clusters with live movement."
                />
                <div className="developing-story-grid">
                  {sections.developingStories.map((cluster) => (
                    <ClusterCard
                      key={cluster.cluster_id}
                      cluster={cluster}
                      to={`/story/${cluster.cluster_id}`}
                      highlighted={highlightedClusterIds.has(cluster.cluster_id)}
                      variant="compact"
                    />
                  ))}
                </div>
              </section>
            )}

            <div className="dashboard-actions">
              <button type="button" className="secondary-button" onClick={() => setShowAllClusters((current) => !current)}>
                {showAllClusters ? "Hide all clusters" : "View all clusters"}
              </button>
            </div>

            {showAllClusters && (
              <section className="dashboard-section" aria-labelledby="all-clusters-heading">
                <SectionHeader
                  id="all-clusters-heading"
                  title="All Clusters"
                  detail="Full fetched result set from the current API request."
                />
                <div className="story-grid">
                  {sections.allClusters.map((cluster) => (
                    <ClusterCard
                      key={cluster.cluster_id}
                      cluster={cluster}
                      to={`/story/${cluster.cluster_id}`}
                      highlighted={highlightedClusterIds.has(cluster.cluster_id)}
                    />
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
