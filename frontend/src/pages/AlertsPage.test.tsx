import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import type { StoryCluster } from "../types";
import { FOLLOWED_STORIES_STORAGE_KEY, type FollowedStoryRecord } from "../utils/followedStories";

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
  return {
    cluster_id: clusterId,
    headline,
    topic: "World",
    summary: `${headline} summary`,
    what_changed: "",
    why_it_matters: "",
    key_facts: [],
    timeline: [
      {
        timestamp: "2026-04-23T00:30:00Z",
        event: `${headline} update`,
        source_url: "https://example.com/a",
        source_title: "Example"
      }
    ],
    timeline_events: [],
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

function saveFollowedRecords(records: FollowedStoryRecord[]) {
  window.localStorage.setItem(FOLLOWED_STORIES_STORAGE_KEY, JSON.stringify(records));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AlertsPage", () => {
  it("shows the empty state for browser-local followed story alerts", () => {
    renderAt("/alerts");

    expect(screen.getByRole("heading", { name: "Followed Stories" })).toBeInTheDocument();
    expect(screen.getByText("No alerts yet")).toBeInTheDocument();
    expect(screen.getByText(/Follow a story from its detail page/)).toBeInTheDocument();
    expect(screen.getAllByText(/push notifications/)).toHaveLength(2);
  });

  it("lists followed stories and allows unfollowing", async () => {
    const story = buildCluster("cluster-1", "Transit Plan Advances", {
      primary_image_url: "https://cdn.example.com/transit.jpg"
    });
    saveFollowedRecords([
      {
        cluster_id: "cluster-1",
        followed_at: "2026-04-23T01:00:00Z",
        last_viewed_at: "2026-04-23T01:00:00Z",
        story
      }
    ]);
    mockFetch({
      "/api/clusters/cluster-1": { body: story }
    });

    const { container } = renderAt("/alerts");

    expect(await screen.findByRole("heading", { name: "Followed Stories" })).toBeInTheDocument();
    expect(screen.getByText("1 followed story")).toBeInTheDocument();
    expect(screen.getByText("0 new updates")).toBeInTheDocument();

    const listPanel = screen.getByRole("region", { name: "Followed story alerts" });
    const row = within(listPanel).getByRole("listitem");
    expect(within(row).getByRole("link", { name: "Transit Plan Advances" })).toHaveAttribute("href", "/story/cluster-1");
    expect(row).toHaveTextContent("1 source");
    expect(row).toHaveTextContent("1 update");
    expect(container.querySelector(".saved-story-row__image img")).toHaveAttribute("src", "https://cdn.example.com/transit.jpg");

    fireEvent.click(within(row).getByRole("button", { name: /unfollow story: transit plan advances/i }));

    await waitFor(() => expect(screen.queryByText("Transit Plan Advances")).not.toBeInTheDocument());
    expect(window.localStorage.getItem(FOLLOWED_STORIES_STORAGE_KEY)).toBe("[]");
  });

  it("shows the sidebar badge for unread followed story updates", async () => {
    const story = buildCluster("cluster-1", "Transit Plan Advances", {
      last_updated: "2026-04-23T03:00:00Z"
    });
    saveFollowedRecords([
      {
        cluster_id: "cluster-1",
        followed_at: "2026-04-23T01:00:00Z",
        last_viewed_at: "2026-04-23T02:00:00Z",
        story
      }
    ]);
    mockFetch({
      "/api/clusters/cluster-1": { body: story }
    });

    renderAt("/alerts");

    const alertsLink = screen.getByRole("link", { name: /^Alerts$/ });
    expect(within(alertsLink).getByText("1")).toBeInTheDocument();
    expect(await screen.findByText("New update")).toBeInTheDocument();
    expect(screen.getByText("1 new update")).toBeInTheDocument();
  });
});
