import { describe, expect, it } from "vitest";
import { toClusterListRows } from "./clusterView";
import type { ClusterListResponse } from "../types";

describe("toClusterListRows", () => {
  it("maps list response rows for UI", () => {
    const payload: ClusterListResponse = {
      total: 1,
      limit: 50,
      offset: 0,
      items: [
        {
          cluster_id: "cluster-1",
          headline: "Headline",
          summary: "Long summary text for preview output in the inspector table.",
          what_changed: "changed",
          why_it_matters: "matters",
          key_facts: [],
          timeline: [],
          timeline_events: [],
          sources: [
            {
              article_id: 1,
              title: "Article",
              url: "https://example.com",
              publisher: "Example",
              published_at: "2026-04-22T00:00:00Z"
            }
          ],
          source_count: 1,
          primary_image_url: null,
          thumbnail_urls: [],
          topic: "general",
          region: null,
          story_type: "general",
          first_seen: "2026-04-22T00:00:00Z",
          last_updated: "2026-04-22T02:00:00Z",
          is_developing: true,
          is_breaking: false,
          confidence_score: 0.712,
          related_cluster_ids: [],
          score: 0.712,
          status: "active"
        }
      ]
    };

    const rows = toClusterListRows(payload);
    expect(rows).toHaveLength(1);
    expect(rows[0].clusterId).toBe("cluster-1");
    expect(rows[0].sourceCount).toBe(1);
    expect(rows[0].summaryPreview.length).toBeGreaterThan(0);
  });

  it("uses ASCII truncation for summary previews", () => {
    const payload: ClusterListResponse = {
      total: 1,
      limit: 50,
      offset: 0,
      items: [
        {
          cluster_id: "cluster-2",
          headline: "Headline",
          summary: "x".repeat(300),
          what_changed: "changed",
          why_it_matters: "matters",
          key_facts: [],
          timeline: [],
          timeline_events: [],
          sources: [],
          source_count: 0,
          primary_image_url: null,
          thumbnail_urls: [],
          topic: "general",
          region: null,
          story_type: "general",
          first_seen: "2026-04-22T00:00:00Z",
          last_updated: "2026-04-22T02:00:00Z",
          is_developing: false,
          is_breaking: false,
          confidence_score: 0.712,
          related_cluster_ids: [],
          score: 0.712,
          status: "active"
        }
      ]
    };

    const rows = toClusterListRows(payload);
    expect(rows[0].summaryPreview.endsWith("...")).toBe(true);
    expect(rows[0].summaryPreview.includes("…")).toBe(false);
  });
});
