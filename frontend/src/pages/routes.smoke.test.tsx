import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppLayout, AppRoutes } from "../App";

type MockReply = {
  status?: number;
  body: unknown;
  contentType?: string;
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppLayout>
        <AppRoutes />
      </AppLayout>
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
      if ((reply.contentType || "application/json") === "text/plain") {
        return new Response(String(reply.body), {
          status: reply.status ?? 200,
          headers: { "Content-Type": "text/plain" }
        });
      }

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

const debugCluster = {
  cluster_id: "cluster-1",
  status: "active",
  score: 0.72,
  source_count: 3,
  validation_error: null,
  headline: "Transit Plan Advances",
  summary: "Multiple sources reported new transit budget details.",
  debug_explanation: {
    grouping_reason: "articles grouped by shared entities",
    thresholds: {
      score_threshold: 0.55,
      title_signal_threshold: 0.72,
      entity_overlap_threshold: 1,
      keyword_overlap_threshold: 2,
      min_sources_for_api: 3
    },
    threshold_results: {
      score_threshold_met: true
    },
    top_shared_entities: ["City Council"],
    top_shared_keywords: ["transit", "budget"],
    score_breakdown: {
      average_similarity_score: 0.7,
      average_title_similarity: 0.8,
      average_entity_jaccard: 0.6,
      average_keyword_jaccard: 0.5,
      average_time_proximity: 0.9
    },
    decision_counts: {
      attach_existing_cluster: 2,
      create_new_cluster: 1
    }
  }
};

describe("route smoke tests", () => {
  it("renders cluster list route", async () => {
    mockFetch({
      "/api/clusters": {
        body: {
          total: 1,
          limit: 50,
          offset: 0,
          items: [
            {
              cluster_id: "cluster-1",
              headline: "Transit Plan Advances",
              summary: "Multiple sources reported new transit budget details.",
              what_changed: "More detail was added.",
              why_it_matters: "Impacts transport access.",
              timeline: [],
              sources: [
                {
                  article_id: 1,
                  title: "A",
                  url: "https://example.com/a",
                  publisher: "Example",
                  published_at: "2026-04-22T00:00:00Z"
                }
              ],
              first_seen: "2026-04-22T00:00:00Z",
              last_updated: "2026-04-22T01:00:00Z",
              score: 0.72,
              status: "active"
            }
          ]
        }
      },
      "/debug/clusters": { body: { total: 1, items: [debugCluster] } }
    });

    renderAt("/");
    expect(await screen.findByText("Cluster List")).toBeInTheDocument();
    expect(await screen.findByText("Transit Plan Advances")).toBeInTheDocument();
  });

  it("renders cluster detail route for valid cluster", async () => {
    mockFetch({
      "/api/clusters/cluster-1": {
        body: {
          cluster_id: "cluster-1",
          headline: "Transit Plan Advances",
          summary: "Multiple sources reported new transit budget details.",
          what_changed: "New route details were confirmed.",
          why_it_matters: "Impacts commuters.",
          timeline: [
            {
              timestamp: "2026-04-22T00:30:00Z",
              event: "Publisher added coverage",
              source_url: "https://example.com/a",
              source_title: "Article A"
            }
          ],
          sources: [
            {
              article_id: 1,
              title: "Article A",
              url: "https://example.com/a",
              publisher: "Example",
              published_at: "2026-04-22T00:00:00Z"
            }
          ],
          first_seen: "2026-04-22T00:00:00Z",
          last_updated: "2026-04-22T01:00:00Z",
          score: 0.72,
          status: "active"
        }
      },
      "/debug/clusters": { body: { total: 1, items: [debugCluster] } }
    });

    renderAt("/clusters/cluster-1");
    expect(await screen.findByText("Cluster Detail")).toBeInTheDocument();
    expect(await screen.findByText("Timeline")).toBeInTheDocument();
    expect(await screen.findByText("Sources")).toBeInTheDocument();
  });

  it("renders debug-only fallback when cluster is not API-eligible", async () => {
    mockFetch({
      "/api/clusters/cluster-x": { status: 404, body: { detail: "Cluster not found" } },
      "/debug/clusters": {
        body: {
          total: 1,
          items: [
            {
              ...debugCluster,
              cluster_id: "cluster-x",
              validation_error: "cluster must have at least 3 sources"
            }
          ]
        }
      }
    });

    renderAt("/clusters/cluster-x");
    expect(await screen.findByText("Not API-eligible")).toBeInTheDocument();
    const matches = await screen.findAllByText(/cluster must have at least 3 sources/i);
    expect(matches.length).toBeGreaterThan(0);
  });

  it("renders metrics route", async () => {
    mockFetch({
      "/metrics": {
        contentType: "text/plain",
        body: `
articles_ingested_total 10
articles_deduplicated_total 2
clusters_created_total 3
clusters_updated_total 4
last_ingest_time 1713000000
last_cluster_time 1713000300
`
      }
    });

    renderAt("/metrics");
    expect(await screen.findByText("Basic Metrics")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("articles_ingested_total")).toBeInTheDocument();
      expect(screen.getByText("10")).toBeInTheDocument();
    });
  });
});
