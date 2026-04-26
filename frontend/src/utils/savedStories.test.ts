import { describe, expect, it } from "vitest";
import type { StoryCluster } from "../types";
import {
  parseSavedStories,
  readSavedStories,
  removeSavedStory,
  saveStorySnapshot,
  SAVED_STORIES_STORAGE_KEY,
  sortSavedStories,
  writeSavedStories
} from "./savedStories";

function buildCluster(clusterId: string, headline: string, lastUpdated = "2026-04-23T00:00:00Z"): StoryCluster {
  return {
    cluster_id: clusterId,
    headline,
    topic: "World",
    summary: `${headline} summary`,
    what_changed: "",
    why_it_matters: "",
    key_facts: [],
    timeline: [],
    timeline_events: [],
    sources: [],
    source_count: 0,
    primary_image_url: null,
    thumbnail_urls: [],
    region: null,
    story_type: "general",
    first_seen: "2026-04-23T00:00:00Z",
    last_updated: lastUpdated,
    is_developing: false,
    is_breaking: false,
    confidence_score: 0.8,
    related_cluster_ids: [],
    score: 0.8,
    status: "active"
  };
}

describe("savedStories storage", () => {
  it("saves a story snapshot and writes it to localStorage", () => {
    const records = saveStorySnapshot([], buildCluster("cluster-1", "Transit Plan Advances"), "2026-04-23T01:00:00Z");

    writeSavedStories(records);

    expect(readSavedStories()).toEqual(records);
    expect(window.localStorage.getItem(SAVED_STORIES_STORAGE_KEY)).toContain("Transit Plan Advances");
  });

  it("removes a saved story", () => {
    const records = saveStorySnapshot([], buildCluster("cluster-1", "Transit Plan Advances"), "2026-04-23T01:00:00Z");

    expect(removeSavedStory(records, "cluster-1")).toEqual([]);
  });

  it("preserves the original saved timestamp when refreshing a saved snapshot", () => {
    const original = saveStorySnapshot([], buildCluster("cluster-1", "Original headline"), "2026-04-23T01:00:00Z");
    const refreshed = saveStorySnapshot(original, buildCluster("cluster-1", "Updated headline"), "2026-04-24T01:00:00Z");

    expect(refreshed).toHaveLength(1);
    expect(refreshed[0].saved_at).toBe("2026-04-23T01:00:00Z");
    expect(refreshed[0].story.headline).toBe("Updated headline");
  });

  it("falls back to an empty list for corrupt or invalid localStorage data", () => {
    window.localStorage.setItem(SAVED_STORIES_STORAGE_KEY, "{not-json");

    expect(readSavedStories()).toEqual([]);
    expect(parseSavedStories(JSON.stringify([{ cluster_id: "", saved_at: "bad", story: null }]))).toEqual([]);
  });

  it("sorts saved records newest first", () => {
    const older = saveStorySnapshot([], buildCluster("cluster-older", "Older story"), "2026-04-23T01:00:00Z")[0];
    const newer = saveStorySnapshot([], buildCluster("cluster-newer", "Newer story"), "2026-04-24T01:00:00Z")[0];

    expect(sortSavedStories([older, newer]).map((record) => record.cluster_id)).toEqual(["cluster-newer", "cluster-older"]);
  });
});
