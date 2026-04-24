import type { ClusterListResponse } from "../types";

export interface ClusterListRow {
  clusterId: string;
  headline: string;
  topic: string;
  sourceCount: number;
  firstSeen: string;
  lastUpdated: string;
  score: number;
  summaryPreview: string;
}

function preview(text: string, maxLength: number): string {
  const trimmed = text.trim();
  if (trimmed.length <= maxLength) {
    return trimmed;
  }
  return `${trimmed.slice(0, maxLength - 3).trimEnd()}...`;
}

export function toClusterListRows(payload: ClusterListResponse): ClusterListRow[] {
  return payload.items.map((item) => ({
    clusterId: item.cluster_id,
    headline: item.headline,
    topic: item.topic,
    sourceCount: item.sources.length,
    firstSeen: item.first_seen,
    lastUpdated: item.last_updated,
    score: item.score,
    summaryPreview: preview(item.summary, 160)
  }));
}
