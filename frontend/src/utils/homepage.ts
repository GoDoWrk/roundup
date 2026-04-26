import type { StoryCluster } from "../types";

const RECENT_UPDATE_WINDOW_MS = 60 * 60 * 1000;
const SUMMARY_PREVIEW_LENGTH = 180;
const TOP_SUPPORTING_COUNT = 3;
const DEVELOPING_STORY_COUNT = 4;
const GENERATED_PLACEHOLDER_TEXT = new Set([
  "pending headline",
  "pending summary",
  "pending change",
  "pending impact"
]);

export function readerText(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) {
    return null;
  }

  const normalized = trimmed.toLowerCase();
  if (GENERATED_PLACEHOLDER_TEXT.has(normalized) || normalized.startsWith("pending ")) {
    return null;
  }

  return trimmed;
}

export function previewSummary(text: string, maxLength = SUMMARY_PREVIEW_LENGTH): string {
  const trimmed = text.trim();
  if (trimmed.length <= maxLength) {
    return trimmed;
  }

  return `${trimmed.slice(0, maxLength - 1).trimEnd()}...`;
}

function parseTimestamp(value: string): number {
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : Number.NEGATIVE_INFINITY;
}

function scoreValue(score: number): number {
  return Number.isFinite(score) ? score : Number.NEGATIVE_INFINITY;
}

export function sortClustersForHomepage(clusters: StoryCluster[]): StoryCluster[] {
  return [...clusters].sort((left, right) => {
    const scoreDiff = scoreValue(right.score) - scoreValue(left.score);
    if (Math.abs(scoreDiff) > 1e-9) {
      return scoreDiff > 0 ? 1 : -1;
    }

    const updatedDiff = parseTimestamp(right.last_updated) - parseTimestamp(left.last_updated);
    if (updatedDiff !== 0) {
      return updatedDiff;
    }

    return left.cluster_id.localeCompare(right.cluster_id);
  });
}

export function sortClustersByLatestUpdates(clusters: StoryCluster[]): StoryCluster[] {
  return [...clusters].sort((left, right) => {
    const updatedDiff = parseTimestamp(right.last_updated) - parseTimestamp(left.last_updated);
    if (updatedDiff !== 0) {
      return updatedDiff;
    }

    const scoreDiff = scoreValue(right.score) - scoreValue(left.score);
    if (Math.abs(scoreDiff) > 1e-9) {
      return scoreDiff > 0 ? 1 : -1;
    }

    return left.cluster_id.localeCompare(right.cluster_id);
  });
}

export function collectTopics(clusters: StoryCluster[]): string[] {
  const topics = new Set<string>();

  for (const cluster of clusters) {
    const topic = cluster.topic?.trim();
    if (topic) {
      topics.add(topic);
    }
  }

  return Array.from(topics).sort((left, right) => left.localeCompare(right));
}

export function clusterMatchesTopic(cluster: StoryCluster, topic: string): boolean {
  if (topic === "all") {
    return true;
  }

  return cluster.topic?.trim() === topic;
}

export function getFilteredClusters(clusters: StoryCluster[], topic: string): StoryCluster[] {
  if (topic === "all") {
    return clusters;
  }

  return clusters.filter((cluster) => clusterMatchesTopic(cluster, topic));
}

export function getClusterImageUrl(cluster: StoryCluster): string | null {
  const primary = cluster.primary_image_url?.trim();
  if (primary) {
    return primary;
  }

  const fallback = cluster.thumbnail_urls?.find((url) => url.trim().length > 0);
  return fallback?.trim() || null;
}

export function getUpdateCount(cluster: StoryCluster): number {
  const timelineEvents = cluster.timeline_events ?? [];
  if (timelineEvents.length > 0) {
    return timelineEvents.length;
  }

  return (cluster.timeline ?? []).length;
}

export function compareDevelopingClusters(left: StoryCluster, right: StoryCluster): number {
  if (left.is_developing !== right.is_developing) {
    return left.is_developing ? -1 : 1;
  }

  const updatedDiff = parseTimestamp(right.last_updated) - parseTimestamp(left.last_updated);
  if (updatedDiff !== 0) {
    return updatedDiff;
  }

  const scoreDiff = scoreValue(right.score) - scoreValue(left.score);
  if (Math.abs(scoreDiff) > 1e-9) {
    return scoreDiff > 0 ? 1 : -1;
  }

  return left.cluster_id.localeCompare(right.cluster_id);
}

export interface HomepageSections {
  leadStory: StoryCluster | null;
  supportingStories: StoryCluster[];
  developingStories: StoryCluster[];
  allClusters: StoryCluster[];
}

export function selectHomepageSections(clusters: StoryCluster[], sortMode: "top" | "latest"): HomepageSections {
  const allClusters = sortMode === "latest" ? sortClustersByLatestUpdates(clusters) : sortClustersForHomepage(clusters);
  const leadStory = allClusters[0] ?? null;
  const supportingStories = allClusters.slice(1, 1 + TOP_SUPPORTING_COUNT);
  const usedTopStoryIds = new Set([leadStory?.cluster_id, ...supportingStories.map((cluster) => cluster.cluster_id)]);

  const developingStories = [...clusters]
    .filter((cluster) => !usedTopStoryIds.has(cluster.cluster_id))
    .sort(compareDevelopingClusters)
    .slice(0, DEVELOPING_STORY_COUNT);

  return {
    leadStory,
    supportingStories,
    developingStories,
    allClusters
  };
}

export function isRecentlyUpdated(lastUpdated: string, referenceTime = Date.now()): boolean {
  const updatedAt = Date.parse(lastUpdated);
  if (!Number.isFinite(updatedAt)) {
    return false;
  }

  return referenceTime - updatedAt <= RECENT_UPDATE_WINDOW_MS;
}

export function getFreshnessLabel(lastUpdated: string, referenceTime = Date.now()): string | null {
  const updatedAt = Date.parse(lastUpdated);
  if (!Number.isFinite(updatedAt)) {
    return null;
  }

  const diffMs = referenceTime - updatedAt;
  if (diffMs < 60 * 1000) {
    return "Updated just now";
  }

  const diffMinutes = Math.floor(diffMs / 60000);
  if (diffMinutes < 60) {
    return `Updated ${diffMinutes}m ago`;
  }

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `Updated ${diffHours}h ago`;
  }

  const diffDays = Math.floor(diffHours / 24);
  return `Updated ${diffDays}d ago`;
}

export function collectSourcePublishers(clusters: StoryCluster[]): string[] {
  const publishers = new Set<string>();

  for (const cluster of clusters) {
    for (const source of cluster.sources) {
      const publisher = source.publisher.trim();
      if (publisher) {
        publishers.add(publisher);
      }
    }
  }

  return Array.from(publishers).sort((left, right) => left.localeCompare(right));
}

export function clusterMatchesPublisher(cluster: StoryCluster, publisher: string): boolean {
  if (publisher === "all") {
    return true;
  }

  return cluster.sources.some((source) => source.publisher.trim() === publisher);
}

export function getChangedClusterIds(
  previousSnapshots: Map<string, string>,
  currentClusters: StoryCluster[]
): Set<string> {
  if (previousSnapshots.size === 0) {
    return new Set();
  }

  const changed = new Set<string>();
  for (const cluster of currentClusters) {
    if (previousSnapshots.get(cluster.cluster_id) !== cluster.last_updated) {
      changed.add(cluster.cluster_id);
    }
  }

  return changed;
}
