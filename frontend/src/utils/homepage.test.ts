import { describe, expect, it } from "vitest";
import type { StoryCluster } from "../types";
import {
  collectSourcePublishers,
  collectTopics,
  getChangedClusterIds,
  getClusterImageUrl,
  getFilteredClusters,
  getUpdateCount,
  previewSummary,
  selectHomepageSections,
  sortClustersByLatestUpdates,
  sortClustersForHomepage
} from "./homepage";

function cluster(overrides: Partial<StoryCluster> & Pick<StoryCluster, "cluster_id" | "headline">): StoryCluster {
  const { cluster_id, headline, ...rest } = overrides;
  return {
    cluster_id,
    headline,
    summary: "Summary",
    what_changed: "",
    why_it_matters: "",
    key_facts: [],
    timeline: [],
    timeline_events: [],
    sources: [],
    source_count: 0,
    primary_image_url: null,
    thumbnail_urls: [],
    topic: "World",
    region: null,
    story_type: "general",
    first_seen: "2026-04-23T00:00:00Z",
    last_updated: "2026-04-23T00:00:00Z",
    is_developing: false,
    is_breaking: false,
    confidence_score: 0,
    related_cluster_ids: [],
    score: 0,
    status: "active",
    ...rest
  };
}

describe("homepage utilities", () => {
  it("sorts clusters by score and freshness", () => {
    const ordered = sortClustersForHomepage([
      cluster({
        cluster_id: "a",
        headline: "A",
        last_updated: "2026-04-23T00:30:00Z",
        score: 0.7
      }),
      cluster({
        cluster_id: "b",
        headline: "B",
        last_updated: "2026-04-23T01:00:00Z",
        score: 0.8
      }),
      cluster({
        cluster_id: "c",
        headline: "C",
        last_updated: "2026-04-23T02:00:00Z",
        score: 0.7
      })
    ]);

    expect(ordered.map((item) => item.cluster_id)).toEqual(["b", "c", "a"]);
  });

  it("sorts clusters by latest update independently", () => {
    const ordered = sortClustersByLatestUpdates([
      cluster({
        cluster_id: "a",
        headline: "A",
        last_updated: "2026-04-23T00:30:00Z",
        score: 0.95
      }),
      cluster({
        cluster_id: "b",
        headline: "B",
        last_updated: "2026-04-23T02:00:00Z",
        score: 0.7
      })
    ]);

    expect(ordered.map((item) => item.cluster_id)).toEqual(["b", "a"]);
  });

  it("collects and filters topics from real cluster fields", () => {
    const clusters = [
      cluster({ cluster_id: "a", headline: "A", topic: "Technology" }),
      cluster({ cluster_id: "b", headline: "B", topic: "World" }),
      cluster({ cluster_id: "c", headline: "C", topic: "Technology" })
    ];

    expect(collectTopics(clusters)).toEqual(["Technology", "World"]);
    expect(getFilteredClusters(clusters, "Technology").map((item) => item.cluster_id)).toEqual(["a", "c"]);
    expect(getFilteredClusters(clusters, "all")).toHaveLength(3);
  });

  it("still collects source publishers for existing public surfaces", () => {
    const clusters = [
      cluster({
        cluster_id: "a",
        headline: "A",
        sources: [
          {
            article_id: 1,
            title: "One",
            url: "https://example.com/1",
            publisher: "Example News",
            published_at: "2026-04-23T00:00:00Z"
          }
        ]
      }),
      cluster({
        cluster_id: "b",
        headline: "B",
        sources: [
          {
            article_id: 2,
            title: "Two",
            url: "https://example.com/2",
            publisher: "Wire Service",
            published_at: "2026-04-23T00:00:00Z"
          }
        ]
      })
    ];

    expect(collectSourcePublishers(clusters)).toEqual(["Example News", "Wire Service"]);
  });

  it("selects lead, supporting, and developing homepage sections", () => {
    const sections = selectHomepageSections(
      [
        cluster({ cluster_id: "lead", headline: "Lead", score: 0.99 }),
        cluster({ cluster_id: "support-1", headline: "Support 1", score: 0.9 }),
        cluster({ cluster_id: "support-2", headline: "Support 2", score: 0.8 }),
        cluster({ cluster_id: "support-3", headline: "Support 3", score: 0.7 }),
        cluster({
          cluster_id: "developing-old",
          headline: "Developing old",
          is_developing: true,
          last_updated: "2026-04-23T01:00:00Z"
        }),
        cluster({
          cluster_id: "developing-new",
          headline: "Developing new",
          is_developing: true,
          last_updated: "2026-04-23T02:00:00Z"
        }),
        cluster({
          cluster_id: "active-new",
          headline: "Active new",
          last_updated: "2026-04-23T03:00:00Z"
        })
      ],
      "top"
    );

    expect(sections.leadStory?.cluster_id).toBe("lead");
    expect(sections.supportingStories.map((item) => item.cluster_id)).toEqual(["support-1", "support-2", "support-3"]);
    expect(sections.developingStories.map((item) => item.cluster_id)).toEqual([
      "developing-new",
      "developing-old",
      "active-new"
    ]);
  });

  it("uses primary images before thumbnail fallbacks", () => {
    expect(
      getClusterImageUrl(
        cluster({
          cluster_id: "a",
          headline: "A",
          primary_image_url: " https://example.com/primary.jpg ",
          thumbnail_urls: ["https://example.com/thumb.jpg"]
        })
      )
    ).toBe("https://example.com/primary.jpg");

    expect(
      getClusterImageUrl(
        cluster({
          cluster_id: "b",
          headline: "B",
          primary_image_url: null,
          sources: [
            {
              article_id: 1,
              title: "B source",
              url: "https://example.com/b",
              publisher: "Example",
              published_at: "2026-04-23T00:00:00Z",
              image_url: " https://example.com/source.jpg "
            }
          ],
          thumbnail_urls: ["", "https://example.com/thumb.jpg"]
        })
      )
    ).toBe("https://example.com/source.jpg");

    expect(
      getClusterImageUrl(
        cluster({
          cluster_id: "c",
          headline: "C",
          primary_image_url: null,
          thumbnail_urls: ["", "https://example.com/thumb.jpg"]
        })
      )
    ).toBe("https://example.com/thumb.jpg");
  });

  it("derives update count from timeline_events before timeline", () => {
    const timelineEvent = {
      timestamp: "2026-04-23T00:30:00Z",
      event: "Update",
      source_url: "https://example.com",
      source_title: "Example"
    };

    expect(
      getUpdateCount(
        cluster({
          cluster_id: "a",
          headline: "A",
          timeline_events: [timelineEvent, { ...timelineEvent, timestamp: "2026-04-23T00:40:00Z" }],
          timeline: [timelineEvent]
        })
      )
    ).toBe(2);

    expect(
      getUpdateCount(
        cluster({
          cluster_id: "b",
          headline: "B",
          timeline_events: [],
          timeline: [timelineEvent]
        })
      )
    ).toBe(1);
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
        last_updated: "2026-04-23T00:30:00Z"
      }),
      cluster({
        cluster_id: "b",
        headline: "B",
        last_updated: "2026-04-23T02:00:00Z"
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
