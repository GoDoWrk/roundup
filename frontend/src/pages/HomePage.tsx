import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiErrorDetails, fetchHomepageClusters, type ApiErrorDetails } from "../api/client";
import { ClusterCard } from "../components/ClusterCard";
import { FeedControls } from "../components/FeedControls";
import type { HomepageClustersResponse, StoryCluster } from "../types";
import { formatReadableTimestamp, formatRelativeTime } from "../utils/format";
import {
  collectTopics,
  compareDevelopingClusters,
  getChangedClusterIds,
  hasClusterImage,
  getFilteredClusters,
  sortClustersByLatestUpdates,
  sortClustersForHomepage
} from "../utils/homepage";

const REFRESH_INTERVAL_MS = 5 * 60_000;

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
  const [homepageData, setHomepageData] = useState<HomepageClustersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorDetails, setErrorDetails] = useState<ApiErrorDetails | null>(null);
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
      const response = await fetchHomepageClusters();
      const items = [
        ...response.sections.top_stories,
        ...response.sections.developing_stories,
        ...response.sections.just_in
      ];
      const changedIds = getChangedClusterIds(previousSnapshotRef.current, items);
      const currentSnapshot = new Map<string, string>();

      for (const cluster of items) {
        currentSnapshot.set(cluster.cluster_id, cluster.last_updated);
      }

      previousSnapshotRef.current = currentSnapshot;
      setHomepageData(response);
      setClusters(items);
      setLastLoadedAt(Date.now());
      setHighlightedClusterIds(changedIds);
      setUpdatedSinceLastRefresh(changedIds.size);
      setErrorDetails(null);
    } catch (err) {
      setErrorDetails(apiErrorDetails(err));
      if (!background) {
        setClusters([]);
        setHomepageData(null);
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
  const error = errorDetails?.message ?? null;

  useEffect(() => {
    if (topicFilter !== "all" && !topics.includes(topicFilter)) {
      setTopicFilter("all");
    }
  }, [topicFilter, topics]);

  const sections = useMemo(() => {
    if (!homepageData) {
      return {
        topStories: [] as StoryCluster[],
        developingStories: [] as StoryCluster[],
        justIn: [] as StoryCluster[],
        allClusters: [] as StoryCluster[]
      };
    }

    const imageReady = (items: StoryCluster[]) => getFilteredClusters(items, topicFilter).filter(hasClusterImage);
    const rank = sortMode === "latest" ? sortClustersByLatestUpdates : sortClustersForHomepage;
    const topStories = rank(imageReady(homepageData.sections.top_stories));
    const developingStories = [...imageReady(homepageData.sections.developing_stories)].sort(compareDevelopingClusters);
    const justIn = sortClustersByLatestUpdates(imageReady(homepageData.sections.just_in));
    const allClusters = [...topStories, ...developingStories, ...justIn];
    return { topStories, developingStories, justIn, allClusters };
  }, [homepageData, sortMode, topicFilter]);

  const visibleCount = sections.allClusters.length;
  const rawSectionCount = homepageData
    ? homepageData.sections.top_stories.length +
      homepageData.sections.developing_stories.length +
      homepageData.sections.just_in.length
    : 0;
  const leadStory = sections.topStories[0] ?? null;
  const supportingStories = sections.topStories.slice(1, 4);
  const hasStories = visibleCount > 0;
  const hasLoadedData = clusters.length > 0 || homepageData !== null || lastLoadedAt !== null;
  const hasNoApiClusters =
    homepageData !== null &&
    rawSectionCount === 0 &&
    homepageData.status.visible_clusters === 0 &&
    homepageData.status.candidate_clusters === 0;
  const hasOnlyNonImageReadyClusters = homepageData !== null && rawSectionCount > 0 && visibleCount === 0;
  const topicFilterLabel = topicFilter === "all" ? "All topics" : topicFilter;
  const lastCheckedReadable = lastLoadedAt ? formatReadableTimestamp(lastLoadedAt) : null;
  const lastIngestionLabel = homepageData?.status.last_ingestion
    ? `Last ingestion ${formatRelativeTime(homepageData.status.last_ingestion, Date.now())}`
    : "Last ingestion unavailable";
  const lastCheckedLabel = lastLoadedAt
    ? `Updated ${formatRelativeTime(lastLoadedAt, Date.now())}${lastCheckedReadable ? ` | ${lastCheckedReadable}` : ""}`
    : "Waiting for live data";
  const liveCountLabel =
    visibleCount === 0
      ? hasLoadedData && topicFilter !== "all"
        ? `No stories in ${topicFilterLabel}`
        : "No live stories"
      : homepageData && topicFilter === "all"
        ? `${homepageData.status.visible_clusters} visible | ${homepageData.status.candidate_clusters} candidates`
        : `${visibleCount} live ${visibleCount === 1 ? "cluster" : "clusters"}`;
  const sortLabel = sortMode === "latest" ? "Latest Updates" : "Top Stories";

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
          {homepageData && <span>{homepageData.status.articles_stored_latest_run} stored latest run</span>}
          {homepageData && <span>{homepageData.status.active_sources} active sources</span>}
          {homepageData && <span>{homepageData.status.articles_pending} articles pending</span>}
          <span>{lastIngestionLabel}</span>
          <span>{lastCheckedLabel}</span>
          <span>{refreshing ? "Live refresh in progress" : "Auto refresh every 5m"}</span>
          <span>Sort: {sortLabel}</span>
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

        {!loading && !error && !hasStories && hasLoadedData && topicFilter === "all" && hasNoApiClusters && (
          <section className="state-panel">
            <p className="eyebrow">Nothing to show yet</p>
            <h2>No stories available yet</h2>
            <p>
              The API is reachable, but <code>/api/clusters/homepage</code> returned no public or candidate clusters.
            </p>
          </section>
        )}

        {!loading && !error && !hasStories && hasLoadedData && topicFilter === "all" && hasOnlyNonImageReadyClusters && (
          <section className="state-panel">
            <p className="eyebrow">No image-ready stories</p>
            <h2>Clusters loaded, but none have usable images</h2>
            <p>
              The API returned {rawSectionCount} {rawSectionCount === 1 ? "cluster" : "clusters"}. The public feed hides
              image-less stories; Inspector can still show them.
            </p>
          </section>
        )}

        {!loading && !hasStories && error && (
          <section className="state-panel state-panel--error" role="alert">
            <p className="eyebrow">{errorDetails?.title ?? "API error"}</p>
            <h2>{errorDetails?.kind === "network" ? "Could not reach Roundup" : "Could not load live stories"}</h2>
            <p>{errorDetails?.message}</p>
            {errorDetails?.endpoint && (
              <p className="muted">
                Endpoint: <code>{errorDetails.endpoint}</code>
              </p>
            )}
            {errorDetails?.action && <p>{errorDetails.action}</p>}
          </section>
        )}

        {hasStories && (
          <>
            {leadStory && (
              <section className="dashboard-section" aria-labelledby="top-stories-heading">
                <SectionHeader id="top-stories-heading" title="Top Stories" detail="Promoted multi-source clusters." />
                <div className="top-stories-layout">
                  <ClusterCard
                    cluster={leadStory}
                    to={`/story/${leadStory.cluster_id}`}
                    highlighted={highlightedClusterIds.has(leadStory.cluster_id)}
                    variant="lead"
                  />
                  {supportingStories.length > 0 && (
                    <div className="supporting-story-stack" aria-label="Supporting top stories">
                      {supportingStories.map((cluster) => (
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
            )}

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

            {sections.justIn.length > 0 && (
              <section className="dashboard-section" aria-labelledby="just-in-heading">
                <SectionHeader
                  id="just-in-heading"
                  title="Just In"
                  detail="Candidate activity, including single-source stories, kept separate from promoted stories."
                />
                <div className="just-in-grid">
                  {sections.justIn.map((cluster) => (
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
                      to={cluster.visibility === "candidate" ? undefined : `/story/${cluster.cluster_id}`}
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
