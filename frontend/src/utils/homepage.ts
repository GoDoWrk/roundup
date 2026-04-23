import type { StoryCluster } from "../types";

const RECENT_UPDATE_WINDOW_MS = 60 * 60 * 1000;
const SUMMARY_PREVIEW_LENGTH = 180;

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

export function getFilteredClusters(clusters: StoryCluster[], publisher: string): StoryCluster[] {
  if (publisher === "all") {
    return clusters;
  }

  return clusters.filter((cluster) => clusterMatchesPublisher(cluster, publisher));
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
