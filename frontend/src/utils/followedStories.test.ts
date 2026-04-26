import { describe, expect, it } from "vitest";
import type { StoryCluster } from "../types";
import {
  FOLLOWED_STORIES_STORAGE_KEY,
  followStorySnapshot,
  formatUnreadCount,
  getUnreadFollowedCount,
  isStoryUnread,
  parseFollowedStories,
  readFollowedStories,
  removeFollowedStory,
  updateFollowedStorySnapshot,
  writeFollowedStories
} from "./followedStories";

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

describe("followedStories storage", () => {
  it("follows a story snapshot and writes it to localStorage", () => {
    const records = followStorySnapshot([], buildCluster("cluster-1", "Transit Plan Advances"), "2026-04-23T01:00:00Z");

    writeFollowedStories(records);

    expect(readFollowedStories()).toEqual(records);
    expect(window.localStorage.getItem(FOLLOWED_STORIES_STORAGE_KEY)).toContain("Transit Plan Advances");
    expect(records[0].last_viewed_at).toBe("2026-04-23T00:00:00Z");
  });

  it("unfollows a story", () => {
    const records = followStorySnapshot([], buildCluster("cluster-1", "Transit Plan Advances"), "2026-04-23T01:00:00Z");

    expect(removeFollowedStory(records, "cluster-1")).toEqual([]);
  });

  it("updates a followed snapshot without changing the last viewed timestamp", () => {
    const original = followStorySnapshot([], buildCluster("cluster-1", "Original headline"), "2026-04-23T01:00:00Z");
    const refreshed = updateFollowedStorySnapshot(original, buildCluster("cluster-1", "Updated headline", "2026-04-24T01:00:00Z"));

    expect(refreshed).toHaveLength(1);
    expect(refreshed[0].followed_at).toBe("2026-04-23T01:00:00Z");
    expect(refreshed[0].last_viewed_at).toBe("2026-04-23T00:00:00Z");
    expect(refreshed[0].story.headline).toBe("Updated headline");
  });

  it("falls back to an empty list for corrupt or invalid localStorage data", () => {
    window.localStorage.setItem(FOLLOWED_STORIES_STORAGE_KEY, "{not-json");

    expect(readFollowedStories()).toEqual([]);
    expect(parseFollowedStories(JSON.stringify([{ cluster_id: "", followed_at: "bad", last_viewed_at: null, story: null }]))).toEqual([]);
  });

  it("counts unread followed stories when last_updated is newer than last_viewed_at", () => {
    const readRecord = followStorySnapshot([], buildCluster("cluster-read", "Read story", "2026-04-23T01:00:00Z"), "2026-04-23T01:00:00Z")[0];
    const unreadRecord = {
      ...followStorySnapshot([], buildCluster("cluster-unread", "Unread story", "2026-04-23T03:00:00Z"), "2026-04-23T01:00:00Z")[0],
      last_viewed_at: "2026-04-23T02:00:00Z"
    };

    expect(isStoryUnread(readRecord)).toBe(false);
    expect(isStoryUnread(unreadRecord)).toBe(true);
    expect(getUnreadFollowedCount([readRecord, unreadRecord])).toBe(1);
  });

  it("does not mark equal, older, missing, or invalid timestamps as unread", () => {
    const equal = {
      ...followStorySnapshot([], buildCluster("cluster-equal", "Equal story", "2026-04-23T01:00:00Z"), "2026-04-23T01:00:00Z")[0],
      last_viewed_at: "2026-04-23T01:00:00Z"
    };
    const older = {
      ...followStorySnapshot([], buildCluster("cluster-older", "Older story", "2026-04-23T01:00:00Z"), "2026-04-23T01:00:00Z")[0],
      last_viewed_at: "2026-04-23T02:00:00Z"
    };
    const missing = {
      ...followStorySnapshot([], buildCluster("cluster-missing", "Missing story", "2026-04-23T01:00:00Z"), "2026-04-23T01:00:00Z")[0],
      last_viewed_at: null
    };
    const invalid = {
      ...followStorySnapshot([], buildCluster("cluster-invalid", "Invalid story", "not-a-date"), "2026-04-23T01:00:00Z")[0],
      last_viewed_at: "2026-04-23T02:00:00Z"
    };

    expect(getUnreadFollowedCount([equal, older, missing, invalid])).toBe(0);
    expect(formatUnreadCount(10)).toBe("9+");
  });
});
