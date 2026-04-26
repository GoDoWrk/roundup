import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchClusterList } from "../api/client";
import { FeedControls } from "../components/FeedControls";
import { ClusterCard } from "../components/ClusterCard";
import type { StoryCluster } from "../types";
import { formatReadableTimestamp, formatRelativeTime } from "../utils/format";
import {
  collectSourcePublishers,
  getChangedClusterIds,
  getFilteredClusters,
  sortClustersByLatestUpdates,
  sortClustersForHomepage
} from "../utils/homepage";

const PAGE_LIMIT = 20;
const REFRESH_INTERVAL_MS = 30_000;

type SortMode = "top" | "latest";

function SkeletonCard() {
  return (
    <article className="story-card story-card--skeleton" aria-hidden="true">
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
    </article>
  );
}

export function HomePage() {
  const [clusters, setClusters] = useState<StoryCluster[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastLoadedAt, setLastLoadedAt] = useState<number | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("top");
  const [publisherFilter, setPublisherFilter] = useState("all");
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
      const response = await fetchClusterList({ limit: PAGE_LIMIT, offset: 0 });
      const changedIds = getChangedClusterIds(previousSnapshotRef.current, response.items);
      const currentSnapshot = new Map<string, string>();

      for (const cluster of response.items) {
        currentSnapshot.set(cluster.cluster_id, cluster.last_updated);
      }

      previousSnapshotRef.current = currentSnapshot;
      setClusters(response.items);
      setTotal(response.total);
      setLastLoadedAt(Date.now());
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

  const publishers = useMemo(() => collectSourcePublishers(clusters), [clusters]);

  useEffect(() => {
    if (publisherFilter !== "all" && !publishers.includes(publisherFilter)) {
      setPublisherFilter("all");
    }
  }, [publisherFilter, publishers]);

  const visibleClusters = useMemo(() => {
    const filtered = getFilteredClusters(clusters, publisherFilter);
    const sorted = sortMode === "latest" ? sortClustersByLatestUpdates(filtered) : sortClustersForHomepage(filtered);
    return sorted.slice(0, PAGE_LIMIT);
  }, [clusters, publisherFilter, sortMode]);

  const visibleCount = visibleClusters.length;
  const hasStories = visibleCount > 0;
  const hasLoadedData = clusters.length > 0 || total > 0 || lastLoadedAt !== null;
  const sourceFilterLabel = publisherFilter === "all" ? "All sources" : publisherFilter;
  const lastCheckedReadable = lastLoadedAt ? formatReadableTimestamp(lastLoadedAt) : null;
  const lastCheckedLabel = lastLoadedAt
    ? `Last checked ${formatRelativeTime(lastLoadedAt, Date.now())}${lastCheckedReadable ? ` | ${lastCheckedReadable}` : ""}`
    : "Waiting for the first live update";
  const liveCountLabel =
    visibleCount === 0
      ? hasLoadedData && publisherFilter !== "all"
        ? `No stories from ${sourceFilterLabel}`
        : "No live stories"
      : total > visibleCount
        ? `Showing ${visibleCount} of ${total} live stories`
        : `${visibleCount} live ${visibleCount === 1 ? "story" : "stories"}`;
  const sortLabel = sortMode === "latest" ? "Latest updates" : "Top / Most Important";

  return (
    <div className="public-page">
      <header className="public-hero">
        <div className="public-hero__copy">
          <p className="eyebrow">Updated live</p>
          <h1>Top Stories</h1>
          <p>Current story clusters ranked by importance and freshness.</p>
        </div>

        <div className="public-hero__actions">
          <button type="button" className="primary-button" onClick={() => void load(true)} disabled={loading || refreshing}>
            {loading || refreshing ? "Updating..." : "Refresh"}
          </button>
        </div>

        <div className="public-hero__meta" aria-live="polite">
          <span>{liveCountLabel}</span>
          <span>{lastCheckedLabel}</span>
          <span>{refreshing ? "Live refresh in progress" : "Auto-refreshes every 30s"}</span>
          <span>{sortLabel}</span>
          {publisherFilter !== "all" && <span>{sourceFilterLabel}</span>}
          {updatedSinceLastRefresh > 0 && (
            <span className="public-hero__accent">{updatedSinceLastRefresh} updated since last refresh</span>
          )}
        </div>
      </header>

      <FeedControls
        sortMode={sortMode}
        publishers={publishers}
        publisherFilter={publisherFilter}
        onSortModeChange={setSortMode}
        onPublisherFilterChange={setPublisherFilter}
      />

      <main className="public-feed">
        {error && hasStories && (
          <div className="banner banner--warning" role="status">
            Live refresh failed: {error}. Showing the last successful results.
          </div>
        )}

        {loading && !hasLoadedData && (
          <section className="state-panel state-panel--loading" aria-busy="true">
            <p className="eyebrow">Loading live feed</p>
            <h2>Checking Roundup for current stories</h2>
            <p>Pulling the latest cluster data and preparing the feed.</p>
            <div className="story-grid story-grid--skeleton" aria-hidden="true">
              {Array.from({ length: 6 }).map((_, index) => (
                <SkeletonCard key={index} />
              ))}
            </div>
          </section>
        )}

        {!loading && !error && !hasStories && hasLoadedData && publisherFilter !== "all" && (
          <section className="state-panel">
            <p className="eyebrow">Filtered view</p>
            <h2>No stories from {publisherFilter}</h2>
            <p>Try a different source filter or return to all stories to keep scanning the live feed.</p>
            <button className="secondary-action" onClick={() => setPublisherFilter("all")} type="button">
              Show all stories
            </button>
          </section>
        )}

        {!loading && !error && !hasStories && hasLoadedData && publisherFilter === "all" && (
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
          </section>
        )}

        {hasStories && (
          <section className="story-grid" aria-label="Live story clusters">
            {visibleClusters.map((cluster) => (
              <ClusterCard
                key={cluster.cluster_id}
                cluster={cluster}
                to={`/story/${cluster.cluster_id}`}
                highlighted={highlightedClusterIds.has(cluster.cluster_id)}
              />
            ))}
          </section>
        )}
      </main>
    </div>
  );
}
