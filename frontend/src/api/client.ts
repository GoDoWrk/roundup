import type {
  ClusterDebugResponse,
  ClusterListResponse,
  HomepageClustersResponse,
  SearchResponse,
  SourceListResponse,
  StoryCluster
} from "../types";

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

export async function fetchClusterList(options: { limit?: number; offset?: number } = {}): Promise<ClusterListResponse> {
  const limit = options.limit ?? 100;
  const offset = options.offset ?? 0;
  return fetchJson<ClusterListResponse>(`/api/clusters?limit=${limit}&offset=${offset}`);
}

export async function fetchHomepageClusters(): Promise<HomepageClustersResponse> {
  return fetchJson<HomepageClustersResponse>("/api/clusters/homepage");
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

export async function fetchSearchResults(options: { q: string; limit?: number }): Promise<SearchResponse> {
  const params = new URLSearchParams();
  params.set("q", options.q);
  params.set("limit", String(options.limit ?? 50));
  return fetchJson<SearchResponse>(`/api/search?${params.toString()}`);
}

export async function fetchSources(): Promise<SourceListResponse> {
  return fetchJson<SourceListResponse>("/api/sources");
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
