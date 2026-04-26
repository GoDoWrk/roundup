import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchClusterList } from "../api/client";
import { ClusterCard } from "../components/ClusterCard";
import { FeedControls } from "../components/FeedControls";
import type { StoryCluster } from "../types";
import { formatReadableTimestamp, formatRelativeTime } from "../utils/format";
import {
  collectTopics,
  getChangedClusterIds,
  getFilteredClusters,
  selectHomepageSections
} from "../utils/homepage";

const PAGE_LIMIT = 20;
const REFRESH_INTERVAL_MS = 30_000;

type SortMode = "top" | "latest";

function SkeletonCard({ variant = "standard" }: { variant?: "standard" | "lead" | "supporting" | "thumbnail" }) {
  return (
    <article className={`story-card story-card--${variant} story-card--skeleton`} aria-hidden="true">
      <div className="story-card__image-frame" />
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

function SectionHeader({ id, title, detail }: { id: string; title: string; detail?: string }) {
  return (
    <div className="dashboard-section__header">
      <h2 id={id}>{title}</h2>
      {detail && <p>{detail}</p>}
    </div>
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
  const lastCheckedReadable = lastLoadedAt ? formatReadableTimestamp(lastLoadedAt) : null;
  const lastCheckedLabel = lastLoadedAt
    ? `Updated ${formatRelativeTime(lastLoadedAt, Date.now())}${lastCheckedReadable ? ` | ${lastCheckedReadable}` : ""}`
    : "Waiting for live data";
  const liveCountLabel =
    visibleCount === 0
      ? hasLoadedData && topicFilter !== "all"
        ? `No stories in ${topicFilterLabel}`
        : "No live stories"
      : total > visibleCount && topicFilter === "all"
        ? `Showing ${visibleCount} of ${total} clusters`
        : `${visibleCount} live ${visibleCount === 1 ? "cluster" : "clusters"}`;
  const sortLabel = sortMode === "latest" ? "Latest" : "Relevance";

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
          <span>{liveCountLabel}</span>
          <span>{lastCheckedLabel}</span>
          <span>{refreshing ? "Live refresh in progress" : "Auto-refreshes every 30s"}</span>
          <span>Sort: {sortLabel}</span>
          <span>Topic: {topicFilterLabel}</span>
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
          </div>
        )}

        {loading && !hasLoadedData && (
          <section className="state-panel state-panel--loading" aria-busy="true">
            <p className="eyebrow">Loading live feed</p>
            <h2>Checking Roundup for current stories</h2>
            <p>Pulling the latest cluster data and preparing the dashboard.</p>
            <div className="top-stories-layout top-stories-layout--skeleton" aria-hidden="true">
              <SkeletonCard variant="lead" />
              <div className="supporting-story-stack">
                {Array.from({ length: 3 }).map((_, index) => (
                  <SkeletonCard key={index} variant="supporting" />
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
                  variant="lead"
                />
                {sections.supportingStories.length > 0 && (
                  <div className="supporting-story-stack" aria-label="Supporting top stories">
                    {sections.supportingStories.map((cluster) => (
                      <ClusterCard
                        key={cluster.cluster_id}
                        cluster={cluster}
                        to={`/story/${cluster.cluster_id}`}
                        highlighted={highlightedClusterIds.has(cluster.cluster_id)}
                        variant="supporting"
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
                      variant="thumbnail"
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
