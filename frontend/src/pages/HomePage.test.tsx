import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HomePage } from "./HomePage";

type Reply = {
  status?: number;
  body: unknown;
};

function renderHome() {
  return render(
    <MemoryRouter>
      <HomePage />
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

function buildCluster(clusterId: string, headline: string, score: number, lastUpdated: string) {
  return {
    cluster_id: clusterId,
    headline,
    summary: `${headline} summary`,
    what_changed: "What changed",
    why_it_matters: "Why it matters",
    timeline: [],
    sources: [
      {
        article_id: Number(clusterId.slice(-1)) || 1,
        title: `${headline} article`,
        url: "https://example.com",
        publisher: "Example",
        published_at: "2026-04-23T00:00:00Z"
      }
    ],
    first_seen: "2026-04-23T00:00:00Z",
    last_updated: lastUpdated,
    score,
    status: "active" as const
  };
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
    resolveFetch(
      jsonResponse({
        total: 0,
        limit: 20,
        offset: 0,
        items: []
      })
    );
    await waitFor(() => expect(screen.getByText("No live stories available")).toBeInTheDocument());
  });

  it("renders an empty state when the API returns no clusters", async () => {
    mockFetch({
      status: 200,
      body: {
        total: 0,
        limit: 20,
        offset: 0,
        items: []
      }
    });

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

  it("sorts by importance by default and can switch to latest updates", async () => {
    mockFetch({
      status: 200,
      body: {
        total: 2,
        limit: 20,
        offset: 0,
        items: [
          buildCluster("cluster-1", "Older but higher score", 0.95, "2026-04-23T00:30:00Z"),
          buildCluster("cluster-2", "Newer but lower score", 0.7, "2026-04-23T02:30:00Z")
        ]
      }
    });

    renderHome();

    const cards = await screen.findAllByTestId("story-card");
    expect(cards[0]).toHaveTextContent("Older but higher score");

    const latestButton = screen.getByRole("button", { name: /latest updates/i });
    fireEvent.click(latestButton);

    await waitFor(() => {
      const updatedCards = screen.getAllByTestId("story-card");
      expect(updatedCards[0]).toHaveTextContent("Newer but lower score");
    });
  });

  it("filters the homepage by source publisher", async () => {
    mockFetch({
      status: 200,
      body: {
        total: 2,
        limit: 20,
        offset: 0,
        items: [
          {
            ...buildCluster("cluster-1", "Example story", 0.9, "2026-04-23T02:00:00Z"),
            sources: [
              {
                article_id: 1,
                title: "Example story article",
                url: "https://example.com",
                publisher: "Example News",
                published_at: "2026-04-23T00:00:00Z"
              }
            ]
          },
          {
            ...buildCluster("cluster-2", "Wire story", 0.8, "2026-04-23T02:30:00Z"),
            sources: [
              {
                article_id: 2,
                title: "Wire story article",
                url: "https://example.com/2",
                publisher: "Wire Service",
                published_at: "2026-04-23T01:00:00Z"
              }
            ]
          }
        ]
      }
    });

    renderHome();
    expect(await screen.findByText("Example story")).toBeInTheDocument();

    const sourceSelect = screen.getByLabelText("Source");
    fireEvent.change(sourceSelect, { target: { value: "Wire Service" } });

    expect(await screen.findByText("Wire story")).toBeInTheDocument();
    expect(screen.queryByText("Example story")).not.toBeInTheDocument();
  });

  it("refreshes the feed on an interval", async () => {
    const responses = [
      {
        total: 1,
        limit: 20,
        offset: 0,
        items: [buildCluster("cluster-1", "Transit Plan Advances", 0.72, "2026-04-23T00:30:00Z")]
      },
      {
        total: 1,
        limit: 20,
        offset: 0,
        items: [buildCluster("cluster-1", "Transit Plan Revised", 0.78, "2026-04-23T01:30:00Z")]
      }
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
