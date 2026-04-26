import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SavedStoriesProvider } from "../context/SavedStoriesContext";
import type { StoryCluster } from "../types";
import { HomePage } from "./HomePage";

type Reply = {
  status?: number;
  body: unknown;
};

function renderHome() {
  return render(
    <MemoryRouter>
      <SavedStoriesProvider>
        <HomePage />
      </SavedStoriesProvider>
    </MemoryRouter>
  );
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function mockFetch(reply: Reply | (() => Promise<Response>)) {
  if (typeof reply === "function") {
    vi.stubGlobal("fetch", vi.fn(reply));
    return;
  }

  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse(reply.body, reply.status ?? 200))
  );
}

function buildCluster(
  clusterId: string,
  headline: string,
  score: number,
  lastUpdated: string,
  overrides: Partial<StoryCluster> = {}
): StoryCluster {
  const updateEvent = {
    timestamp: lastUpdated,
    event: `${headline} update`,
    source_url: "https://example.com",
    source_title: `${headline} article`
  };

  return {
    cluster_id: clusterId,
    headline,
    topic: "World",
    summary: `${headline} summary`,
    what_changed: "What changed",
    why_it_matters: "Why it matters",
    key_facts: [],
    timeline: [updateEvent],
    timeline_events: [updateEvent],
    sources: [
      {
        article_id: Number(clusterId.replace(/\D/g, "")) || 1,
        title: `${headline} article`,
        url: "https://example.com",
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
    last_updated: lastUpdated,
    is_developing: false,
    is_breaking: false,
    confidence_score: score,
    related_cluster_ids: [],
    score,
    status: "active",
    ...overrides
  };
}

function clusterResponse(items: StoryCluster[]) {
  return {
    total: items.length,
    limit: 20,
    offset: 0,
    items
  };
}

function leadCard() {
  return screen.getAllByTestId("story-card").find((card) => card.getAttribute("data-card-variant") === "lead");
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("HomePage", () => {
  it("shows a loading state while the request is pending", async () => {
    let resolveFetch!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn(() => pending));

    renderHome();
    expect(await screen.findByText("Checking Roundup for current stories")).toBeInTheDocument();
    resolveFetch(jsonResponse(clusterResponse([])));
    await waitFor(() => expect(screen.getByText("No live stories available")).toBeInTheDocument());
  });

  it("renders an empty state when the API returns no clusters", async () => {
    mockFetch({ status: 200, body: clusterResponse([]) });

    renderHome();
    expect(await screen.findByText("No live stories available")).toBeInTheDocument();
  });

  it("renders an error state when the API request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("server error", { status: 500 }))
    );

    renderHome();
    expect(await screen.findByText("Could not load live stories")).toBeInTheDocument();
    expect(screen.getByText(/returned 500/i)).toBeInTheDocument();
  });

  it("uses the highest relevance cluster as the default lead story and renders supporting stories", async () => {
    mockFetch({
      status: 200,
      body: clusterResponse([
        buildCluster("cluster-1", "Lower score story", 0.7, "2026-04-23T02:30:00Z"),
        buildCluster("cluster-2", "Highest score story", 0.95, "2026-04-23T00:30:00Z", {
          primary_image_url: "https://example.com/lead.jpg",
          source_count: 3
        }),
        buildCluster("cluster-3", "Second supporting story", 0.85, "2026-04-23T01:30:00Z"),
        buildCluster("cluster-4", "Third supporting story", 0.82, "2026-04-23T01:00:00Z")
      ])
    });

    renderHome();

    const topStories = await screen.findByRole("region", { name: "Top Stories" });
    const cards = within(topStories).getAllByTestId("story-card");
    expect(cards[0]).toHaveAttribute("data-card-variant", "lead");
    expect(cards[0]).toHaveTextContent("Highest score story");
    expect(cards[0]).toHaveTextContent("3 sources");
    expect(within(cards[0]).getByRole("link", { name: /highest score story/i })).toHaveAttribute("href", "/story/cluster-2");
    expect(cards[1]).toHaveTextContent("Second supporting story");
    expect(cards[0].querySelector("img")).toHaveAttribute("src", "https://example.com/lead.jpg");
  });

  it("saves and unsaves a homepage story card with local persistence", async () => {
    mockFetch({
      status: 200,
      body: clusterResponse([buildCluster("cluster-1", "Saveable story", 0.9, "2026-04-23T02:00:00Z")])
    });

    renderHome();
    await screen.findByText("Saveable story");

    fireEvent.click(screen.getByRole("button", { name: /save story: saveable story/i }));

    expect(screen.getByRole("button", { name: /remove saved story: saveable story/i })).toHaveAttribute("aria-pressed", "true");
    expect(window.localStorage.getItem("roundup-saved-stories-v1")).toContain("Saveable story");

    fireEvent.click(screen.getByRole("button", { name: /remove saved story: saveable story/i }));

    expect(screen.getByRole("button", { name: /save story: saveable story/i })).toHaveAttribute("aria-pressed", "false");
    expect(window.localStorage.getItem("roundup-saved-stories-v1")).toBe("[]");
  });

  it("can switch from relevance sorting to latest sorting", async () => {
    mockFetch({
      status: 200,
      body: clusterResponse([
        buildCluster("cluster-1", "Older but higher score", 0.95, "2026-04-23T00:30:00Z"),
        buildCluster("cluster-2", "Newer but lower score", 0.7, "2026-04-23T02:30:00Z")
      ])
    });

    renderHome();
    await waitFor(() => expect(leadCard()).toHaveTextContent("Older but higher score"));

    fireEvent.click(screen.getByRole("button", { name: /sort: latest/i }));

    await waitFor(() => expect(leadCard()).toHaveTextContent("Newer but lower score"));
  });

  it("filters the homepage by real cluster topic values", async () => {
    mockFetch({
      status: 200,
      body: clusterResponse([
        buildCluster("cluster-1", "World story", 0.9, "2026-04-23T02:00:00Z", { topic: "World" }),
        buildCluster("cluster-2", "Technology story", 0.8, "2026-04-23T02:30:00Z", { topic: "Technology" })
      ])
    });

    renderHome();
    expect(await screen.findByText("World story")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "Technology" } });

    expect(await screen.findByText("Technology story")).toBeInTheDocument();
    expect(screen.queryByText("World story")).not.toBeInTheDocument();
  });

  it("prioritizes developing stories by is_developing and latest update after top stories", async () => {
    mockFetch({
      status: 200,
      body: clusterResponse([
        buildCluster("cluster-1", "Lead", 0.99, "2026-04-23T00:00:00Z"),
        buildCluster("cluster-2", "Support one", 0.9, "2026-04-23T00:00:00Z"),
        buildCluster("cluster-3", "Support two", 0.89, "2026-04-23T00:00:00Z"),
        buildCluster("cluster-4", "Support three", 0.88, "2026-04-23T00:00:00Z"),
        buildCluster("cluster-5", "Developing older", 0.5, "2026-04-23T01:00:00Z", { is_developing: true }),
        buildCluster("cluster-6", "Developing newer", 0.4, "2026-04-23T03:00:00Z", { is_developing: true }),
        buildCluster("cluster-7", "Recent active", 0.7, "2026-04-23T04:00:00Z")
      ])
    });

    renderHome();

    const developing = await screen.findByRole("region", { name: "Developing Stories" });
    const cards = within(developing).getAllByTestId("story-card");
    expect(cards[0]).toHaveTextContent("Developing newer");
    expect(cards[1]).toHaveTextContent("Developing older");
    expect(cards[2]).toHaveTextContent("Recent active");
  });

  it("renders a placeholder visual when no image is available", async () => {
    mockFetch({
      status: 200,
      body: clusterResponse([buildCluster("cluster-1", "Image missing story", 0.9, "2026-04-23T02:00:00Z")])
    });

    renderHome();
    await screen.findByText("Image missing story");

    const lead = leadCard();
    expect(lead).toBeTruthy();
    expect((lead as HTMLElement).querySelector("img")).toBeNull();
    expect(within(lead as HTMLElement).getByText("W")).toBeInTheDocument();
  });

  it("expands all fetched clusters from the View all clusters action", async () => {
    const items = [
      buildCluster("cluster-1", "Story one", 0.99, "2026-04-23T00:00:00Z"),
      buildCluster("cluster-2", "Story two", 0.9, "2026-04-23T01:00:00Z"),
      buildCluster("cluster-3", "Story three", 0.8, "2026-04-23T02:00:00Z")
    ];
    mockFetch({ status: 200, body: clusterResponse(items) });

    renderHome();
    await screen.findByText("Story one");
    expect(screen.queryByRole("region", { name: "All Clusters" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View all clusters" }));

    const allClusters = await screen.findByRole("region", { name: "All Clusters" });
    expect(within(allClusters).getAllByTestId("story-card")).toHaveLength(3);
  });

  it("refreshes the feed on an interval", async () => {
    const responses = [
      clusterResponse([buildCluster("cluster-1", "Transit Plan Advances", 0.72, "2026-04-23T00:30:00Z")]),
      clusterResponse([buildCluster("cluster-1", "Transit Plan Revised", 0.78, "2026-04-23T01:30:00Z")])
    ];

    const intervalHandlers: Array<() => void> = [];
    vi.spyOn(window, "setInterval").mockImplementation(((handler: TimerHandler) => {
      intervalHandlers.push(() => {
        if (typeof handler === "function") {
          handler();
        }
      });

      return 1 as unknown as number;
    }) as typeof window.setInterval);

    let callCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        const payload = responses[Math.min(callCount, responses.length - 1)];
        callCount += 1;
        return jsonResponse(payload);
      })
    );

    renderHome();
    await waitFor(() => expect(screen.getByText("Transit Plan Advances")).toBeInTheDocument());
    expect(callCount).toBe(1);

    await act(async () => {
      intervalHandlers[0]?.();
    });

    await waitFor(() => expect(screen.getByText("Transit Plan Revised")).toBeInTheDocument());
    expect(screen.getByText("Updated since last refresh")).toBeInTheDocument();
    expect(callCount).toBe(2);
  });
});
