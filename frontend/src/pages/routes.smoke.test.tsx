import { fireEvent, render, screen, within } from "@testing-library/react";
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
      primary_entity_overlap_required: true,
      keyword_overlap_threshold: 2,
      topic_semantic_score_threshold: 0.38,
      attach_override_title_similarity_threshold: 0.3,
      attach_override_time_proximity_threshold: 0.8,
      min_sources_for_api: 3,
      min_sources_for_top_stories: 2,
      min_sources_for_developing_stories: 2
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
      average_semantic_score: 0.7,
      average_time_proximity: 0.9,
      score_formula: "0.45*title_similarity + 0.25*entity_jaccard + 0.20*keyword_jaccard + 0.10*time_proximity",
      semantic_formula: "0.50*title_similarity + 0.30*entity_jaccard + 0.20*keyword_jaccard"
    },
    decision_counts: {
      attach_existing_cluster: 2,
      create_new_cluster: 1
    },
    recent_join_decisions: [],
    source_quality_summary: {},
    warnings: []
  }
};

describe("route smoke tests", () => {
  it("renders the public homepage at /", async () => {
    mockFetch({
      "/api/clusters/homepage": {
        body: {
          sections: {
            top_stories: [
              {
                cluster_id: "cluster-1",
                headline: "Transit Plan Advances",
                summary: "Multiple sources reported new transit budget details.",
                what_changed: "More detail was added.",
                why_it_matters: "Impacts transport access.",
                key_facts: [],
                timeline: [],
                timeline_events: [],
                sources: [
                  {
                    article_id: 1,
                    title: "A",
                    url: "https://example.com/a",
                    publisher: "Example",
                    published_at: "2026-04-22T00:00:00Z"
                  }
                ],
                source_count: 1,
                primary_image_url: "https://images.example.com/transit.jpg",
                thumbnail_urls: ["https://images.example.com/transit.jpg"],
                topic: "Transit",
                region: null,
                story_type: "general",
                first_seen: "2026-04-22T00:00:00Z",
                last_updated: "2026-04-22T01:00:00Z",
                is_developing: true,
                is_breaking: false,
                confidence_score: 0.72,
                related_cluster_ids: [],
                score: 0.72,
                status: "active"
              }
            ],
            developing_stories: [],
            just_in: []
          },
          status: {
            visible_clusters: 1,
            candidate_clusters: 0,
            articles_fetched_latest_run: 1,
            articles_stored_latest_run: 1,
            duplicate_articles_skipped_latest_run: 0,
            failed_source_count: 0,
            active_sources: 1,
            last_ingestion: "2026-04-22T01:00:00Z",
            articles_pending: 0,
            summaries_pending: 0
          },
          thresholds: {
            min_sources_for_top_stories: 2,
            min_sources_for_developing_stories: 2,
            show_just_in_single_source: true,
            max_top_stories: 6,
            max_developing_stories: 8,
            max_just_in: 10
          }
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
      "/api/clusters/homepage": {
        body: {
          sections: {
            top_stories: [
            {
              cluster_id: "cluster-1",
              headline: "Transit Plan Advances",
              summary: "Multiple sources reported new transit budget details.",
              what_changed: "More detail was added.",
              why_it_matters: "Impacts transport access.",
              key_facts: [],
              timeline: [],
              timeline_events: [],
              sources: [
                {
                  article_id: 1,
                  title: "A",
                  url: "https://example.com/a",
                  publisher: "Example",
                  published_at: "2026-04-22T00:00:00Z"
                }
              ],
              source_count: 1,
              primary_image_url: "https://images.example.com/transit.jpg",
              thumbnail_urls: ["https://images.example.com/transit.jpg"],
              topic: "Transit",
              region: null,
              story_type: "general",
              first_seen: "2026-04-22T00:00:00Z",
              last_updated: "2026-04-22T01:00:00Z",
              is_developing: true,
              is_breaking: false,
              confidence_score: 0.72,
              related_cluster_ids: [],
              score: 0.72,
              status: "active"
            }
            ],
            developing_stories: [],
            just_in: []
          },
          status: {
            visible_clusters: 1,
            candidate_clusters: 0,
            articles_fetched_latest_run: 1,
            articles_stored_latest_run: 1,
            duplicate_articles_skipped_latest_run: 0,
            failed_source_count: 0,
            active_sources: 1,
            last_ingestion: "2026-04-22T01:00:00Z",
            articles_pending: 0,
            summaries_pending: 0
          },
          thresholds: {
            min_sources_for_top_stories: 2,
            min_sources_for_developing_stories: 2,
            show_just_in_single_source: true,
            max_top_stories: 6,
            max_developing_stories: 8,
            max_just_in: 10
          }
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

  it("redirects the hidden clusters route to the homepage", async () => {
    renderAt("/clusters");

    expect(screen.getByRole("complementary", { name: /roundup navigation/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Top Stories" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Home$/ })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: /^Clusters$/ })).not.toBeInTheDocument();
  });

  it("redirects the hidden alerts route to saved stories", async () => {
    renderAt("/alerts");

    expect(screen.getByRole("complementary", { name: /roundup navigation/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Saved Stories" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Saved$/ })).toHaveAttribute("aria-current", "page");
  });

  it("renders the public search page at /search", async () => {
    renderAt("/search");

    expect(screen.getByRole("complementary", { name: /roundup navigation/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Find stories, updates, and sources" })).toBeInTheDocument();
    expect(screen.getByText("Search live Roundup data")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Search$/ })).not.toBeInTheDocument();
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
    expect(screen.getByRole("tab", { name: "Sources" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Alerts" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Display" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /^Settings$/ }).some((link) => link.getAttribute("aria-current") === "page")).toBe(
      true
    );
  });

  it("keeps primary navigation limited to current product surfaces", async () => {
    renderAt("/settings");

    const primaryNav = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(within(primaryNav).getByRole("link", { name: /^Home$/ })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: /^Saved$/ })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: /^Inspector$/ })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: /^Settings$/ })).toBeInTheDocument();
    expect(within(primaryNav).queryByRole("link", { name: /^Search$/ })).not.toBeInTheDocument();
    expect(within(primaryNav).queryByRole("link", { name: /^Alerts$/ })).not.toBeInTheDocument();
    expect(within(primaryNav).queryByRole("link", { name: /^Clusters$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Topics" })).not.toBeInTheDocument();
  });

  it("redirects hidden topic routes to the homepage", async () => {
    renderAt("/topic/world");

    expect(screen.getByRole("complementary", { name: /roundup navigation/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Top Stories" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Home$/ })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: /^World$/ })).not.toBeInTheDocument();
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
      "/debug/clusters": { body: { total: 1, items: [debugCluster] } }
    });

    renderAt("/inspect");
    expect(screen.queryByRole("complementary", { name: /roundup navigation/i })).not.toBeInTheDocument();
    expect(await screen.findByText("Roundup Inspector")).toBeInTheDocument();
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
