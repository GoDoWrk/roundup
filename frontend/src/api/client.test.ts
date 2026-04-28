import { afterEach, describe, expect, it, vi } from "vitest";
import { apiErrorDetails, fetchClusterList, fetchHomepageClusters, RoundupApiError } from "./client";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    statusText: status === 200 ? "OK" : "Server Error",
    headers: { "Content-Type": "application/json" }
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("uses the expected cluster list endpoint and validates the items array", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ total: 0, limit: 25, offset: 5, items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchClusterList({ limit: 25, offset: 5 });

    expect(fetchMock).toHaveBeenCalledWith("/api/clusters?limit=25&offset=5", {
      headers: { Accept: "application/json" }
    });
    expect(result.items).toEqual([]);
  });

  it("turns network failures into an explicit backend unavailable error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));

    await expect(fetchHomepageClusters()).rejects.toMatchObject({
      name: "RoundupApiError",
      kind: "network",
      endpoint: "/api/clusters/homepage",
      status: null
    });
  });

  it("describes network failures without exposing raw browser fetch wording", async () => {
    const error = new RoundupApiError("Roundup API is unavailable at the local Roundup API proxy.", {
      endpoint: "/api/clusters/homepage",
      kind: "network",
      status: null
    });

    const details = apiErrorDetails(error);

    expect(details.title).toBe("Backend unavailable");
    expect(details.kind).toBe("network");
    expect(details.endpoint).toBe("/api/clusters/homepage");
    expect(details.action).toContain("docker compose up --build");
    expect(details.message).not.toContain("Failed to fetch");
  });

  it("keeps HTTP API failures separate from backend unavailable failures", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("server error", { status: 500, statusText: "Server Error" })));

    await expect(fetchHomepageClusters()).rejects.toMatchObject({
      name: "RoundupApiError",
      kind: "http",
      status: 500
    });
  });

  it("treats gateway proxy failures as backend unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("Roundup API proxy could not reach http://localhost:8000.", { status: 502 }))
    );

    await expect(fetchHomepageClusters()).rejects.toMatchObject({
      name: "RoundupApiError",
      kind: "network",
      status: 502,
      endpoint: "/api/clusters/homepage"
    });
  });

  it("keeps API 503 responses as HTTP errors", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("temporarily unavailable", { status: 503 })));

    await expect(fetchHomepageClusters()).rejects.toMatchObject({
      name: "RoundupApiError",
      kind: "http",
      status: 503,
      endpoint: "/api/clusters/homepage"
    });
  });

  it("rejects malformed homepage responses before page code reads missing arrays", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ sections: {}, status: {} })));

    await expect(fetchHomepageClusters()).rejects.toBeInstanceOf(RoundupApiError);
    await expect(fetchHomepageClusters()).rejects.toMatchObject({
      kind: "invalid_response",
      endpoint: "/api/clusters/homepage"
    });
  });
});
