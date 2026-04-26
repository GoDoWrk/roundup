import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import type { SearchResponse } from "../types";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>
  );
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function searchResult(overrides: Partial<SearchResponse["items"][number]> = {}): SearchResponse["items"][number] {
  return {
    id: "cluster:cluster-1:story",
    type: "cluster",
    cluster_id: "cluster-1",
    title: "Transit Plan Advances",
    snippet: "City leaders approved a transit funding plan.",
    topic: "Transit",
    thumbnail_url: null,
    source_name: "Example News",
    source_count: 3,
    update_count: 2,
    last_updated: "2026-04-23T01:00:00Z",
    article_url: null,
    published_at: null,
    matched_field: "headline",
    ...overrides
  };
}

function searchResponse(items: SearchResponse["items"], query = "transit"): SearchResponse {
  return {
    query,
    total: items.length,
    limit: 50,
    counts: {
      all: items.length,
      clusters: items.filter((item) => item.type === "cluster").length,
      updates: items.filter((item) => item.type === "update").length,
      sources: items.filter((item) => item.type === "source").length
    },
    items
  };
}

function mockSearch(reply: SearchResponse | { status: number; body: unknown } | (() => Promise<Response>)) {
  if (typeof reply === "function") {
    vi.stubGlobal("fetch", vi.fn(reply));
    return;
  }

  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      if ("status" in reply) {
        return jsonResponse(reply.body, reply.status);
      }
      return jsonResponse(reply);
    })
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("SearchPage", () => {
  it("renders an empty query state without calling the API", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    renderAt("/search");

    expect(screen.getByRole("heading", { name: "Find stories, updates, and sources" })).toBeInTheDocument();
    expect(screen.getByText("Search live Roundup data")).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("renders real search results and filters them by tab", async () => {
    mockSearch(
      searchResponse([
        searchResult(),
        searchResult({
          id: "update:cluster-1:what_changed",
          type: "update",
          title: "Funding vote moved forward",
          snippet: "Funding negotiations moved into a final public vote.",
          matched_field: "what_changed"
        }),
        searchResult({
          id: "source:cluster-1:5",
          type: "source",
          title: "Reuters reports transit vote",
          snippet: "Reuters",
          source_name: "Reuters",
          article_url: "https://example.com/reuters",
          published_at: "2026-04-23T00:00:00Z",
          matched_field: "publisher"
        })
      ])
    );

    renderAt("/search?q=transit");

    expect(await screen.findByText('Results for "transit"')).toBeInTheDocument();
    expect(screen.getByText("Transit Plan Advances")).toBeInTheDocument();
    expect(screen.getByText("Funding vote moved forward")).toBeInTheDocument();
    expect(screen.getByText("Reuters reports transit vote")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /sources 1/i }));

    const panel = screen.getByRole("region", { name: /results for "transit"/i });
    expect(within(panel).getByText("Reuters reports transit vote")).toBeInTheDocument();
    expect(within(panel).queryByText("Transit Plan Advances")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Funding vote moved forward")).not.toBeInTheDocument();
  });

  it("debounces typed query changes and calls the search endpoint", async () => {
    vi.useFakeTimers();
    mockSearch(searchResponse([searchResult({ title: "Reuters transit report", source_name: "Reuters" })], "Reuters"));

    renderAt("/search");
    fireEvent.change(screen.getByLabelText("Search Roundup"), { target: { value: "Reuters" } });

    await act(async () => {
      vi.advanceTimersByTime(350);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("Reuters transit report")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/search?q=Reuters&limit=50"),
      expect.objectContaining({ headers: { Accept: "application/json" } })
    );
  });

  it("shows a loading state while search is pending", async () => {
    let resolveFetch!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    mockSearch(() => pending);

    renderAt("/search?q=transit");

    expect(await screen.findByText("Find stories, updates, and sources")).toBeInTheDocument();
    expect(document.querySelector(".search-results-list--skeleton")).toBeInTheDocument();

    resolveFetch(jsonResponse(searchResponse([])));
    await waitFor(() => expect(screen.getByText('No results for "transit"')).toBeInTheDocument());
  });

  it("shows no-result and error states", async () => {
    mockSearch(searchResponse([], "unknown"));
    const { unmount } = renderAt("/search?q=unknown");

    expect(await screen.findByText('No results for "unknown"')).toBeInTheDocument();
    unmount();

    mockSearch({ status: 500, body: { detail: "search failed" } });
    renderAt("/search?q=transit");

    expect(await screen.findByText("Could not load search results")).toBeInTheDocument();
    expect(screen.getByText(/returned 500/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry search" })).toBeInTheDocument();
  });
});
