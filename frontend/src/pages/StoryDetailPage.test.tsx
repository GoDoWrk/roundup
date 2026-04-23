import { render, screen } from "@testing-library/react";
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("StoryDetailPage", () => {
  it("renders the full public story detail view", async () => {
    mockFetch({
      "/api/clusters/cluster-1": {
        body: {
          cluster_id: "cluster-1",
          headline: "Transit Plan Advances",
          summary: "A major transit plan moved forward after new budget support and public review.",
          what_changed: "City leaders approved the revised transit budget framework.",
          why_it_matters: "The change affects service frequency and longer-term route planning.",
          timeline: [
            {
              timestamp: "2026-04-22T00:30:00Z",
              event: "Budget language was revised",
              source_url: "https://example.com/a",
              source_title: "Transit Budget Coverage"
            },
            {
              timestamp: "2026-04-22T03:30:00Z",
              event: "Final vote support was reported",
              source_url: "https://example.com/b",
              source_title: "Vote Coverage"
            }
          ],
          sources: [
            {
              article_id: 1,
              title: "Transit Budget Coverage",
              url: "https://example.com/a",
              publisher: "Example News",
              published_at: "2026-04-22T00:00:00Z"
            },
            {
              article_id: 2,
              title: "Vote Coverage",
              url: "https://example.com/b",
              publisher: "Example News",
              published_at: "2026-04-22T03:00:00Z"
            }
          ],
          first_seen: "2026-04-22T00:00:00Z",
          last_updated: "2026-04-22T04:00:00Z",
          score: 0.82,
          status: "active"
        }
      }
    });

    renderAt("/story/cluster-1");

    expect(await screen.findByText("Transit Plan Advances")).toBeInTheDocument();
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("What changed")).toBeInTheDocument();
    expect(screen.getByText("Why it matters")).toBeInTheDocument();
    expect(screen.getByText("Timeline")).toBeInTheDocument();
    expect(screen.getByText("Sources")).toBeInTheDocument();
    expect(screen.getByText("2 sources")).toBeInTheDocument();
  });

  it("hides empty sections when the cluster is partial", async () => {
    mockFetch({
      "/api/clusters/cluster-2": {
        body: {
          cluster_id: "cluster-2",
          headline: "Transit Plan Advances",
          summary: "A short summary is still shown.",
          what_changed: "",
          why_it_matters: "",
          timeline: [],
          sources: [],
          first_seen: "2026-04-22T00:00:00Z",
          last_updated: "2026-04-22T04:00:00Z",
          score: 0.82,
          status: "active"
        }
      }
    });

    renderAt("/story/cluster-2");

    expect(await screen.findByText("Transit Plan Advances")).toBeInTheDocument();
    expect(screen.queryByText("What changed")).not.toBeInTheDocument();
    expect(screen.queryByText("Why it matters")).not.toBeInTheDocument();
    expect(screen.queryByText("Timeline")).not.toBeInTheDocument();
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
  });
});
