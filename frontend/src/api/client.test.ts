import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchClusterList, fetchHomepageClusters, RoundupApiError } from "./client";

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

  it("keeps HTTP API failures separate from backend unavailable failures", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("server error", { status: 500, statusText: "Server Error" })));

    await expect(fetchHomepageClusters()).rejects.toMatchObject({
      name: "RoundupApiError",
      kind: "http",
      status: 500
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
