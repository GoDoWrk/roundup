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
          topic: "Transit Plan",
          summary: "Long summary text for preview output in the inspector table.",
          what_changed: "changed",
          why_it_matters: "matters",
          timeline: [],
          sources: [
            {
              article_id: 1,
              title: "Article",
              url: "https://example.com",
              publisher: "Example",
              published_at: "2026-04-22T00:00:00Z"
            }
          ],
          first_seen: "2026-04-22T00:00:00Z",
          last_updated: "2026-04-22T02:00:00Z",
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
          topic: "Transit Plan",
          summary: "x".repeat(300),
          what_changed: "changed",
          why_it_matters: "matters",
          timeline: [],
          sources: [],
          first_seen: "2026-04-22T00:00:00Z",
          last_updated: "2026-04-22T02:00:00Z",
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
