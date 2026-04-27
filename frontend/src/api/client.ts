import type {
  ClusterDebugResponse,
  ClusterListResponse,
  HomepageClustersResponse,
  HealthResponse,
  SearchResponse,
  SourceListResponse,
  StoryCluster
} from "../types";

type ApiErrorKind = "http" | "network" | "invalid_json" | "invalid_response";

export class RoundupApiError extends Error {
  endpoint: string;
  kind: ApiErrorKind;
  status: number | null;

  constructor(message: string, options: { endpoint: string; kind: ApiErrorKind; status?: number | null }) {
    super(message);
    this.name = "RoundupApiError";
    this.endpoint = options.endpoint;
    this.kind = options.kind;
    this.status = options.status ?? null;
  }
}

const importMetaEnv = (import.meta as ImportMeta & { env?: { VITE_ROUNDUP_API_BASE_URL?: string } }).env;
const API_BASE_URL = (importMetaEnv?.VITE_ROUNDUP_API_BASE_URL ?? "").replace(/\/+$/, "");

function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  return API_BASE_URL ? `${API_BASE_URL}${path}` : path;
}

async function responseText(response: Response): Promise<string> {
  try {
    const text = await response.text();
    return text.trim();
  } catch {
    return "";
  }
}

function unavailableMessage(endpoint: string): string {
  const target = API_BASE_URL || "the local Roundup API proxy";
  return `Roundup API is unavailable at ${target}. Check that Docker Compose is running and ${endpoint} is reachable.`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function assertRecord(value: unknown, endpoint: string): asserts value is Record<string, unknown> {
  if (!isRecord(value)) {
    throw new RoundupApiError(`${endpoint} returned an invalid response shape.`, {
      endpoint,
      kind: "invalid_response"
    });
  }
}

function assertArrayField(value: Record<string, unknown>, key: string, endpoint: string): void {
  if (!Array.isArray(value[key])) {
    throw new RoundupApiError(`${endpoint} returned an invalid response shape: ${key} must be an array.`, {
      endpoint,
      kind: "invalid_response"
    });
  }
}

function assertClusterListResponse(value: ClusterListResponse, endpoint: string): ClusterListResponse {
  assertRecord(value, endpoint);
  assertArrayField(value, "items", endpoint);
  return value as ClusterListResponse;
}

function assertHomepageClustersResponse(value: HomepageClustersResponse, endpoint: string): HomepageClustersResponse {
  assertRecord(value, endpoint);
  const sections = value.sections;
  if (!isRecord(sections)) {
    throw new RoundupApiError(`${endpoint} returned an invalid response shape: sections is missing.`, {
      endpoint,
      kind: "invalid_response"
    });
  }
  const sectionRecord = sections as Record<string, unknown>;
  assertArrayField(sectionRecord, "top_stories", endpoint);
  assertArrayField(sectionRecord, "developing_stories", endpoint);
  assertArrayField(sectionRecord, "just_in", endpoint);
  if (!isRecord(value.status)) {
    throw new RoundupApiError(`${endpoint} returned an invalid response shape: status is missing.`, {
      endpoint,
      kind: "invalid_response"
    });
  }
  return value;
}

function assertDebugClusterResponse(value: ClusterDebugResponse, endpoint: string): ClusterDebugResponse {
  assertRecord(value, endpoint);
  assertArrayField(value, "items", endpoint);
  return value as ClusterDebugResponse;
}

function assertStoryCluster(value: StoryCluster, endpoint: string): StoryCluster {
  assertRecord(value, endpoint);
  assertArrayField(value, "sources", endpoint);
  return value as StoryCluster;
}

async function fetchJson<T>(endpoint: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(endpoint), {
      headers: {
        Accept: "application/json"
      }
    });
  } catch {
    throw new RoundupApiError(unavailableMessage(endpoint), {
      endpoint,
      kind: "network",
      status: null
    });
  }

  if (!response.ok) {
    const message = await responseText(response);
    const statusText = response.statusText ? ` ${response.statusText}` : "";
    throw new RoundupApiError(`${endpoint} returned ${response.status}${statusText}: ${message || "no response body"}`, {
      endpoint,
      kind: "http",
      status: response.status
    });
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new RoundupApiError(`${endpoint} returned invalid JSON.`, {
      endpoint,
      kind: "invalid_json",
      status: response.status
    });
  }
}

export function describeApiError(error: unknown): string {
  if (error instanceof RoundupApiError) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Unknown Roundup API error.";
}

export function apiErrorKind(error: unknown): ApiErrorKind | "unknown" {
  return error instanceof RoundupApiError ? error.kind : "unknown";
}

export async function fetchText(endpoint: string): Promise<string> {
  let response: Response;
  try {
    response = await fetch(apiUrl(endpoint), {
    headers: {
      Accept: "text/plain"
    }
  });
  } catch {
    throw new RoundupApiError(unavailableMessage(endpoint), {
      endpoint,
      kind: "network",
      status: null
    });
  }

  if (!response.ok) {
    const message = await responseText(response);
    const statusText = response.statusText ? ` ${response.statusText}` : "";
    throw new RoundupApiError(`${endpoint} returned ${response.status}${statusText}: ${message || "no response body"}`, {
      endpoint,
      kind: "http",
      status: response.status
    });
  }

  return await response.text();
}

export async function fetchClusterList(options: { limit?: number; offset?: number } = {}): Promise<ClusterListResponse> {
  const limit = options.limit ?? 100;
  const offset = options.offset ?? 0;
  const endpoint = `/api/clusters?limit=${limit}&offset=${offset}`;
  return assertClusterListResponse(await fetchJson<ClusterListResponse>(endpoint), endpoint);
}

export async function fetchHomepageClusters(): Promise<HomepageClustersResponse> {
  const endpoint = "/api/clusters/homepage";
  return assertHomepageClustersResponse(await fetchJson<HomepageClustersResponse>(endpoint), endpoint);
}

export async function fetchClusterDetail(clusterId: string): Promise<StoryCluster | null> {
  const endpoint = `/api/clusters/${clusterId}`;
  let response: Response;
  try {
    response = await fetch(apiUrl(endpoint), {
      headers: { Accept: "application/json" }
    });
  } catch {
    throw new RoundupApiError(unavailableMessage(endpoint), {
      endpoint,
      kind: "network",
      status: null
    });
  }

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    const message = await responseText(response);
    const statusText = response.statusText ? ` ${response.statusText}` : "";
    throw new RoundupApiError(`${endpoint} returned ${response.status}${statusText}: ${message || "no response body"}`, {
      endpoint,
      kind: "http",
      status: response.status
    });
  }

  try {
    return assertStoryCluster((await response.json()) as StoryCluster, endpoint);
  } catch (err) {
    if (err instanceof RoundupApiError) {
      throw err;
    }
    throw new RoundupApiError(`${endpoint} returned invalid JSON.`, {
      endpoint,
      kind: "invalid_json",
      status: response.status
    });
  }
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

export async function fetchHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>("/health");
}

export async function fetchDebugClusters(): Promise<ClusterDebugResponse> {
  const endpoint = "/debug/clusters";
  return assertDebugClusterResponse(await fetchJson<ClusterDebugResponse>(endpoint), endpoint);
}

export async function fetchMetricsText(): Promise<string> {
  return fetchText("/metrics");
}
