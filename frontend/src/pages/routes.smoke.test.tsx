import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";

type MockReply = {
  status?: number;
  body: unknown;
  contentType?: string;
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
  promotion_blockers: [],
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
      topic_semantic_score_threshold: 0.38,
      attach_override_title_similarity_threshold: 0.3,
      attach_override_time_proximity_threshold: 0.8,
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
      average_semantic_score: 0.66,
      average_time_proximity: 0.9,
      score_formula: "0.45*title_similarity + 0.25*entity_jaccard + 0.20*keyword_jaccard + 0.10*time_proximity",
      semantic_formula: "0.50*title_similarity + 0.30*entity_jaccard + 0.20*keyword_jaccard"
    },
    decision_counts: {
      attach_existing_cluster: 2,
      create_new_cluster: 1
    },
    recent_join_decisions: [],
    warnings: []
  }
};

describe("route smoke tests", () => {
  it("renders the public homepage at /", async () => {
    mockFetch({
      "/api/clusters": {
        body: {
          total: 1,
          limit: 20,
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
      }
    });

    renderAt("/");
    expect(screen.getByRole("complementary", { name: /roundup navigation/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Home$/ })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("Top Stories")).toBeInTheDocument();
    expect(await screen.findByText("Transit Plan Advances")).toBeInTheDocument();
  });

  it("clicks through from a homepage card into the public story page", async () => {
    mockFetch({
      "/api/clusters?limit=20&offset=0": {
        body: {
          total: 1,
          limit: 20,
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
      "/api/clusters/cluster-1": {
        body: {
          cluster_id: "cluster-1",
          headline: "Transit Plan Advances",
          summary: "A major transit plan moved forward after new budget support.",
          what_changed: "City leaders approved the revised transit budget framework.",
          why_it_matters: "The change affects service frequency and route planning.",
          timeline: [],
          sources: [
            {
              article_id: 1,
              title: "Transit Budget Coverage",
              url: "https://example.com/a",
              publisher: "Example News",
              published_at: "2026-04-22T00:00:00Z"
            }
          ],
          first_seen: "2026-04-22T00:00:00Z",
          last_updated: "2026-04-22T01:00:00Z",
          score: 0.72,
          status: "active"
        }
      }
    });

    renderAt("/");
    fireEvent.click(await screen.findByRole("link", { name: /transit plan advances/i }));

    expect(screen.getByRole("complementary", { name: /roundup navigation/i })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Back to all clusters" })).toBeInTheDocument();
    expect(await screen.findByText("A major transit plan moved forward after new budget support.")).toBeInTheDocument();
  });

  it.each([
    ["/clusters", "Clusters", /^Clusters$/],
    ["/alerts", "Followed Stories", /^Alerts$/]
  ])("renders public shell placeholder at %s", async (path, title, linkName) => {
    renderAt(path);

    expect(screen.getByRole("complementary", { name: /roundup navigation/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: linkName })).toHaveAttribute("aria-current", "page");
  });

  it("renders the public search page at /search", async () => {
    renderAt("/search");

    expect(screen.getByRole("complementary", { name: /roundup navigation/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Find stories, updates, and sources" })).toBeInTheDocument();
    expect(screen.getByText("Search live Roundup data")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Search$/ })).toHaveAttribute("aria-current", "page");
  });

  it("renders the saved stories page at /saved", async () => {
    renderAt("/saved");

    expect(screen.getByRole("complementary", { name: /roundup navigation/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Saved Stories" })).toBeInTheDocument();
    expect(screen.getByText("Your saved list is empty")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Saved$/ })).toHaveAttribute("aria-current", "page");
  });

  it("renders settings preferences and highlights the settings shortcuts", async () => {
    renderAt("/settings");

    expect(screen.getByRole("complementary", { name: /roundup navigation/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Preferences" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Alerts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Display" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Topics" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /^Settings$/ }).some((link) => link.getAttribute("aria-current") === "page")).toBe(
      true
    );
  });

  it("renders topic placeholder routes and highlights the active topic", async () => {
    renderAt("/topic/world");

    expect(screen.getByRole("complementary", { name: /roundup navigation/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "World" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^World$/ })).toHaveAttribute("aria-current", "page");
  });

  it("renders the inspector cluster list under /inspect", async () => {
    mockFetch({
      "/api/clusters": {
        body: {
          total: 1,
          limit: 100,
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
      "/debug/clusters": { body: { total: 1, items: [debugCluster] } },
      "/health": {
        body: {
          status: "ok",
          app: "roundup",
          db: "ok",
          miniflux_configured: true,
          miniflux_reachable: true,
          miniflux_usable: true,
          runtime: {
            api_workers: 1,
            inspector_worker_processes: 1,
            scheduler_enabled: true,
            scheduler_interval_seconds: 600,
            ingestion_concurrency: 1,
            summarization_concurrency: 1,
            clustering_batch_size: 100,
            clustering_concurrency: 1,
            ingestion_active: true
          },
          timestamp: "2026-04-26T00:00:00Z"
        }
      }
    });

    renderAt("/inspect");
    expect(screen.queryByRole("complementary", { name: /roundup navigation/i })).not.toBeInTheDocument();
    expect(await screen.findByText("Roundup Inspector")).toBeInTheDocument();
    expect(await screen.findByText("System Health")).toBeInTheDocument();
    expect(await screen.findByText("Miniflux")).toBeInTheDocument();
    expect(await screen.findByText("Cluster List")).toBeInTheDocument();
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

    renderAt("/inspect/clusters/cluster-1");
    expect(await screen.findByText("Cluster Detail")).toBeInTheDocument();
    expect(await screen.findByText("Timeline")).toBeInTheDocument();
    expect(await screen.findByText("Sources")).toBeInTheDocument();
  });

  it("redirects legacy cluster detail links into /inspect", async () => {
    mockFetch({
      "/api/clusters/cluster-1": {
        body: {
          cluster_id: "cluster-1",
          headline: "Transit Plan Advances",
          summary: "Multiple sources reported new transit budget details.",
          what_changed: "New route details were confirmed.",
          why_it_matters: "Impacts commuters.",
          timeline: [],
          sources: [],
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
    expect(await screen.findByText("Back to list")).toHaveAttribute("href", "/inspect");
  });

  it("renders metrics route", async () => {
    mockFetch({
      "/metrics": {
        contentType: "text/plain",
        body: `\narticles_ingested_total 10\narticles_deduplicated_total 2\nclusters_created_total 3\nclusters_updated_total 4\nlast_ingest_time 1713000000\nlast_cluster_time 1713000300\n`
      }
    });

    renderAt("/inspect/metrics");
    expect(await screen.findByText("Basic Metrics")).toBeInTheDocument();
  });
});
