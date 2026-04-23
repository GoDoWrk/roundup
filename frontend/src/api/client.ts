import type { ClusterDebugResponse, ClusterListResponse, StoryCluster } from "../types";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json"
    }
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${url} returned ${response.status}: ${message || response.statusText}`);
  }

  return (await response.json()) as T;
}

export async function fetchClusterList(): Promise<ClusterListResponse> {
  return fetchJson<ClusterListResponse>("/api/clusters?limit=100&offset=0");
}

export async function fetchClusterDetail(clusterId: string): Promise<StoryCluster | null> {
  const response = await fetch(`/api/clusters/${clusterId}`, {
    headers: { Accept: "application/json" }
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`/api/clusters/${clusterId} returned ${response.status}: ${message || response.statusText}`);
  }

  return (await response.json()) as StoryCluster;
}

export async function fetchDebugClusters(): Promise<ClusterDebugResponse> {
  return fetchJson<ClusterDebugResponse>("/debug/clusters");
}

export async function fetchMetricsText(): Promise<string> {
  const response = await fetch("/metrics", {
    headers: {
      Accept: "text/plain"
    }
  });

  if (!response.ok) {
    throw new Error(`/metrics returned ${response.status}`);
  }

  return await response.text();
}
