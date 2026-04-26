import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";

type MockReply = {
  status?: number;
  body: unknown;
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>
  );
}

function mockFetch(replies: Record<string, MockReply>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const entry = Object.entries(replies).find(([key]) => url.includes(key));
      if (!entry) {
        return new Response("not found", { status: 404 });
      }

      const [, reply] = entry;
      return new Response(JSON.stringify(reply.body), {
        status: reply.status ?? 200,
        headers: { "Content-Type": "application/json" }
      });
    })
  );
}

function storyPayload(overrides: Record<string, unknown> = {}) {
  return {
    cluster_id: "cluster-1",
    headline: "Transit Plan Advances",
    topic: "Transit",
    summary: "A major transit plan moved forward after new budget support and public review.",
    what_changed: "City leaders approved the revised transit budget framework.",
    why_it_matters: "The change affects service frequency and longer-term route planning.",
    key_facts: ["3 sources are tracking this story, including Example News.", "Recurring themes include transit."],
    timeline: [
      {
        timestamp: "2026-04-22T03:30:00Z",
        event: "Final vote support was reported",
        source_url: "https://example.com/b",
        source_title: "Vote Coverage"
      },
      {
        timestamp: "2026-04-22T00:30:00Z",
        event: "Budget language was revised",
        source_url: "https://example.com/a",
        source_title: "Transit Budget Coverage"
      },
      {
        timestamp: "2026-04-22T02:30:00Z",
        event: "Route impacts were detailed",
        source_url: "https://example.com/c",
        source_title: "Route Coverage"
      },
      {
        timestamp: "2026-04-21T23:30:00Z",
        event: "Initial hearing was scheduled",
        source_url: "https://example.com/d",
        source_title: "Hearing Coverage"
      },
      {
        timestamp: "2026-04-21T22:30:00Z",
        event: "Agency released a planning memo",
        source_url: "https://example.com/e",
        source_title: "Memo Coverage"
      },
      {
        timestamp: "2026-04-21T21:30:00Z",
        event: "Advocates requested additional review",
        source_url: "https://example.com/f",
        source_title: "Advocate Coverage"
      },
      {
        timestamp: "2026-04-21T20:30:00Z",
        event: "Older budget context surfaced",
        source_url: "https://example.com/g",
        source_title: "Older Coverage"
      }
    ],
    timeline_events: [],
    sources: [
      {
        article_id: 1,
        title: "Transit Budget Coverage",
        url: "https://example.com/a",
        publisher: "Example News",
        published_at: "2026-04-22T00:00:00Z",
        image_url: "https://cdn.example.com/hero.jpg"
      },
      {
        article_id: 2,
        title: "Vote Coverage",
        url: "https://example.com/b",
        publisher: "Civic Daily",
        published_at: "2026-04-22T03:00:00Z",
        image_url: "https://cdn.example.com/second.jpg"
      }
    ],
    source_count: 2,
    primary_image_url: "https://cdn.example.com/hero.jpg",
    thumbnail_urls: ["https://cdn.example.com/hero.jpg", "https://cdn.example.com/second.jpg"],
    region: null,
    story_type: "general",
    first_seen: "2026-04-22T00:00:00Z",
    last_updated: "2026-04-22T04:00:00Z",
    is_developing: true,
    is_breaking: false,
    confidence_score: 0.82,
    related_cluster_ids: ["cluster-related", "missing-related"],
    score: 0.82,
    status: "active",
    ...overrides
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("StoryDetailPage", () => {
  it("renders a tabbed story view with newest-first timeline, sources, facts, and related stories", async () => {
    mockFetch({
      "/api/clusters/cluster-1": { body: storyPayload() },
      "/api/clusters/cluster-related": {
        body: storyPayload({
          cluster_id: "cluster-related",
          headline: "Related Transit Story",
          summary: "A related public cluster uses the same live cluster contract.",
          related_cluster_ids: []
        })
      },
      "/api/clusters/missing-related": { status: 404, body: { detail: "Cluster not found" } }
    });

    const { container } = renderAt("/story/cluster-1");

    expect(await screen.findByRole("heading", { name: "Transit Plan Advances" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to all clusters" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("button", { name: "Save story" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More story actions" })).toBeInTheDocument();
    expect(screen.getByText("7 updates")).toBeInTheDocument();
    expect(screen.getByText("2 sources")).toBeInTheDocument();

    const timelinePanel = screen.getByRole("tabpanel");
    expect(within(timelinePanel).getByText("Summary")).toBeInTheDocument();
    expect(within(timelinePanel).getByText("Latest")).toBeInTheDocument();
    const latest = within(timelinePanel).getByText("Final vote support was reported");
    const prior = within(timelinePanel).getByText("Route impacts were detailed");
    expect(latest.compareDocumentPosition(prior) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(timelinePanel).queryByText("Older budget context surfaced")).not.toBeInTheDocument();
    expect(container.querySelectorAll(".story-timeline__thumbnail")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Load older updates" }));
    expect(screen.getByText("Older budget context surfaced")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Key Facts" }));
    expect(screen.getByRole("tab", { name: "Key Facts" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("3 sources are tracking this story, including Example News.")).toBeInTheDocument();
    expect(screen.queryByText("Final vote support was reported")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Sources" }));
    expect(screen.getByText("Example News")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Transit Budget Coverage" })).toHaveAttribute("href", "https://example.com/a");

    fireEvent.click(screen.getByRole("tab", { name: "Related" }));
    expect(await screen.findByText("Related Transit Story")).toBeInTheDocument();
    expect(screen.queryByText("missing-related")).not.toBeInTheDocument();
  });

  it("reflects saved state on story detail and persists save and unsave", async () => {
    mockFetch({
      "/api/clusters/cluster-1": { body: storyPayload({ related_cluster_ids: [] }) }
    });

    renderAt("/story/cluster-1");
    expect(await screen.findByRole("heading", { name: "Transit Plan Advances" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save story" }));

    expect(screen.getByRole("button", { name: "Remove saved story" })).toHaveAttribute("aria-pressed", "true");
    expect(window.localStorage.getItem("roundup-saved-stories-v1")).toContain("Transit Plan Advances");

    fireEvent.click(screen.getByRole("button", { name: "Remove saved story" }));

    expect(screen.getByRole("button", { name: "Save story" })).toHaveAttribute("aria-pressed", "false");
    expect(window.localStorage.getItem("roundup-saved-stories-v1")).toBe("[]");
  });

  it("handles missing optional enrichment fields with graceful tab empty states", async () => {
    mockFetch({
      "/api/clusters/cluster-2": {
        body: storyPayload({
          cluster_id: "cluster-2",
          headline: "Sparse Transit Story",
          key_facts: [],
          timeline: [],
          timeline_events: [],
          sources: [],
          source_count: 0,
          related_cluster_ids: [],
          primary_image_url: null,
          thumbnail_urls: []
        })
      }
    });

    renderAt("/story/cluster-2");

    expect(await screen.findByText("Sparse Transit Story")).toBeInTheDocument();
    expect(screen.getByText("No timeline updates yet")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Key Facts" }));
    expect(screen.getByText("No key facts available")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Sources" }));
    expect(screen.getByText("No sources available")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Related" }));
    expect(screen.getByText("No related stories yet")).toBeInTheDocument();
  });
});
