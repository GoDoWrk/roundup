import { describe, expect, it } from "vitest";
import type { StoryCluster } from "../types";
import {
  collectSourcePublishers,
  getChangedClusterIds,
  getFilteredClusters,
  previewSummary,
  sortClustersByLatestUpdates,
  sortClustersForHomepage
} from "./homepage";

function cluster(overrides: Partial<StoryCluster> & Pick<StoryCluster, "cluster_id" | "headline" | "summary" | "what_changed" | "why_it_matters" | "timeline" | "sources" | "first_seen" | "last_updated" | "score" | "status">): StoryCluster {
  return overrides as StoryCluster;
}

describe("homepage utilities", () => {
  it("sorts clusters by score and freshness", () => {
    const ordered = sortClustersForHomepage([
      cluster({
        cluster_id: "a",
        headline: "A",
        summary: "Summary",
        what_changed: "",
        why_it_matters: "",
        timeline: [],
        sources: [],
        first_seen: "2026-04-23T00:00:00Z",
        last_updated: "2026-04-23T00:30:00Z",
        score: 0.7,
        status: "active"
      }),
      cluster({
        cluster_id: "b",
        headline: "B",
        summary: "Summary",
        what_changed: "",
        why_it_matters: "",
        timeline: [],
        sources: [],
        first_seen: "2026-04-23T00:00:00Z",
        last_updated: "2026-04-23T01:00:00Z",
        score: 0.8,
        status: "active"
      }),
      cluster({
        cluster_id: "c",
        headline: "C",
        summary: "Summary",
        what_changed: "",
        why_it_matters: "",
        timeline: [],
        sources: [],
        first_seen: "2026-04-23T00:00:00Z",
        last_updated: "2026-04-23T02:00:00Z",
        score: 0.7,
        status: "active"
      })
    ]);

    expect(ordered.map((item) => item.cluster_id)).toEqual(["b", "c", "a"]);
  });

  it("sorts clusters by latest update independently", () => {
    const ordered = sortClustersByLatestUpdates([
      cluster({
        cluster_id: "a",
        headline: "A",
        summary: "Summary",
        what_changed: "",
        why_it_matters: "",
        timeline: [],
        sources: [],
        first_seen: "2026-04-23T00:00:00Z",
        last_updated: "2026-04-23T00:30:00Z",
        score: 0.95,
        status: "active"
      }),
      cluster({
        cluster_id: "b",
        headline: "B",
        summary: "Summary",
        what_changed: "",
        why_it_matters: "",
        timeline: [],
        sources: [],
        first_seen: "2026-04-23T00:00:00Z",
        last_updated: "2026-04-23T02:00:00Z",
        score: 0.7,
        status: "active"
      })
    ]);

    expect(ordered.map((item) => item.cluster_id)).toEqual(["b", "a"]);
  });

  it("collects and filters source publishers", () => {
    const clusters = [
      cluster({
        cluster_id: "a",
        headline: "A",
        summary: "Summary",
        what_changed: "",
        why_it_matters: "",
        timeline: [],
        sources: [
          {
            article_id: 1,
            title: "One",
            url: "https://example.com/1",
            publisher: "Example News",
            published_at: "2026-04-23T00:00:00Z"
          }
        ],
        first_seen: "2026-04-23T00:00:00Z",
        last_updated: "2026-04-23T00:30:00Z",
        score: 0.7,
        status: "active"
      }),
      cluster({
        cluster_id: "b",
        headline: "B",
        summary: "Summary",
        what_changed: "",
        why_it_matters: "",
        timeline: [],
        sources: [
          {
            article_id: 2,
            title: "Two",
            url: "https://example.com/2",
            publisher: "Wire Service",
            published_at: "2026-04-23T00:00:00Z"
          }
        ],
        first_seen: "2026-04-23T00:00:00Z",
        last_updated: "2026-04-23T01:30:00Z",
        score: 0.8,
        status: "active"
      })
    ];

    expect(collectSourcePublishers(clusters)).toEqual(["Example News", "Wire Service"]);
    expect(getFilteredClusters(clusters, "Example News").map((item) => item.cluster_id)).toEqual(["a"]);
    expect(getFilteredClusters(clusters, "all")).toHaveLength(2);
  });

  it("detects clusters that changed since the previous refresh", () => {
    const previous = new Map<string, string>([
      ["a", "2026-04-23T00:30:00Z"],
      ["b", "2026-04-23T01:30:00Z"]
    ]);
    const changed = getChangedClusterIds(previous, [
      cluster({
        cluster_id: "a",
        headline: "A",
        summary: "Summary",
        what_changed: "",
        why_it_matters: "",
        timeline: [],
        sources: [],
        first_seen: "2026-04-23T00:00:00Z",
        last_updated: "2026-04-23T00:30:00Z",
        score: 0.7,
        status: "active"
      }),
      cluster({
        cluster_id: "b",
        headline: "B",
        summary: "Summary",
        what_changed: "",
        why_it_matters: "",
        timeline: [],
        sources: [],
        first_seen: "2026-04-23T00:00:00Z",
        last_updated: "2026-04-23T02:00:00Z",
        score: 0.8,
        status: "active"
      })
    ]);

    expect(Array.from(changed)).toEqual(["b"]);
  });

  it("truncates long summaries cleanly", () => {
    const preview = previewSummary("x".repeat(200), 20);
    expect(preview).toHaveLength(22);
    expect(preview.endsWith("...")).toBe(true);
  });
});
