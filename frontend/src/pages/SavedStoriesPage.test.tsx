import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import type { StoryCluster } from "../types";
import { readSavedStories, SAVED_STORIES_STORAGE_KEY, type SavedStoryRecord } from "../utils/savedStories";

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

function mockFetch(replies: Record<string, { status?: number; body: unknown }>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const entry = Object.entries(replies).find(([key]) => url.includes(key));
      if (!entry) {
        return new Response("not found", { status: 404 });
      }

      const [, reply] = entry;
      return jsonResponse(reply.body, reply.status ?? 200);
    })
  );
}

function buildCluster(clusterId: string, headline: string, overrides: Partial<StoryCluster> = {}): StoryCluster {
  const updateEvent = {
    timestamp: "2026-04-23T00:30:00Z",
    event: `${headline} update`,
    source_url: "https://example.com/a",
    source_title: "Example"
  };

  return {
    cluster_id: clusterId,
    headline,
    topic: "World",
    summary: `${headline} summary`,
    what_changed: "",
    why_it_matters: "",
    key_facts: [],
    timeline: [updateEvent],
    timeline_events: [updateEvent],
    sources: [
      {
        article_id: 1,
        title: `${headline} source`,
        url: "https://example.com/a",
        publisher: "Example",
        published_at: "2026-04-23T00:00:00Z"
      }
    ],
    source_count: 1,
    primary_image_url: null,
    thumbnail_urls: [],
    region: null,
    story_type: "general",
    first_seen: "2026-04-23T00:00:00Z",
    last_updated: "2026-04-23T01:00:00Z",
    is_developing: false,
    is_breaking: false,
    confidence_score: 0.8,
    related_cluster_ids: [],
    score: 0.8,
    status: "active",
    ...overrides
  };
}

function saveRecords(records: SavedStoryRecord[]) {
  window.localStorage.setItem(SAVED_STORIES_STORAGE_KEY, JSON.stringify(records));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SavedStoriesPage", () => {
  it("renders a local-browser empty state without alert language", () => {
    renderAt("/saved");

    expect(screen.getByRole("heading", { name: "Saved Stories" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Your saved list is empty" })).toBeInTheDocument();
    expect(screen.getByText("Stories saved in this browser, kept locally without accounts or backend changes.")).toBeInTheDocument();
    expect(
      screen.getByText("Save stories from the homepage or story detail pages to build a local reading list in this browser.")
    ).toBeInTheDocument();
    expect(screen.queryByText(/notification/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/email/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/push/i)).not.toBeInTheDocument();
  });

  it("renders saved stories newest first with metadata, thumbnail, and remove control", async () => {
    const older = buildCluster("cluster-older", "Older saved story");
    const newer = buildCluster("cluster-newer", "Newer saved story", {
      primary_image_url: "https://cdn.example.com/newer.jpg",
      source_count: 3,
      timeline_events: [
        {
          timestamp: "2026-04-23T02:00:00Z",
          event: "First update",
          source_url: "https://example.com/a",
          source_title: "Example"
        },
        {
          timestamp: "2026-04-23T03:00:00Z",
          event: "Second update",
          source_url: "https://example.com/b",
          source_title: "Example"
        }
      ]
    });

    saveRecords([
      { cluster_id: "cluster-older", saved_at: "2026-04-23T01:00:00Z", story: older },
      { cluster_id: "cluster-newer", saved_at: "2026-04-24T01:00:00Z", story: newer }
    ]);
    mockFetch({
      "/api/clusters/cluster-older": { body: older },
      "/api/clusters/cluster-newer": { body: newer }
    });

    const { container } = renderAt("/saved");

    expect(await screen.findByRole("heading", { name: "Saved Stories" })).toBeInTheDocument();
    expect(screen.getByText("2 saved stories")).toBeInTheDocument();
    expect(screen.getByText("Newest first")).toBeInTheDocument();

    const listPanel = screen.getByRole("region", { name: "Saved list" });
    const rows = within(listPanel).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Newer saved story");
    expect(rows[1]).toHaveTextContent("Older saved story");
    expect(rows[0]).toHaveTextContent("3 sources");
    expect(rows[0]).toHaveTextContent("2 updates");
    expect(rows[0]).toHaveTextContent(/Saved/);
    expect(container.querySelector(".saved-story-row__image img")).toHaveAttribute("src", "https://cdn.example.com/newer.jpg");

    fireEvent.click(within(rows[0]).getByRole("button", { name: /remove saved story: newer saved story/i }));

    await waitFor(() => expect(screen.queryByText("Newer saved story")).not.toBeInTheDocument());
    expect(window.localStorage.getItem(SAVED_STORIES_STORAGE_KEY)).not.toContain("Newer saved story");
  });

  it("keeps a local snapshot and marks it when the live story is missing", async () => {
    const stale = buildCluster("cluster-stale", "Stale saved story");
    saveRecords([{ cluster_id: "cluster-stale", saved_at: "2026-04-24T01:00:00Z", story: stale }]);
    expect(readSavedStories()).toHaveLength(1);
    mockFetch({
      "/api/clusters/cluster-stale": { status: 404, body: { detail: "Cluster not found" } }
    });

    renderAt("/saved");

    expect(await screen.findByText("No longer in live feed")).toBeInTheDocument();
    expect(screen.getByText("Stale saved story")).toBeInTheDocument();
    expect(window.localStorage.getItem(SAVED_STORIES_STORAGE_KEY)).toContain("Stale saved story");
  });
});
