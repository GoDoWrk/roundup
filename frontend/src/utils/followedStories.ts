import type { StoryCluster } from "../types";

export const FOLLOWED_STORIES_STORAGE_KEY = "roundup-followed-stories-v1";

export interface FollowedStoryRecord {
  cluster_id: string;
  followed_at: string;
  last_viewed_at: string | null;
  story: StoryCluster;
}

function parseTime(value: string | null | undefined): number {
  if (!value) {
    return Number.NaN;
  }

  const time = Date.parse(value);
  return Number.isFinite(time) ? time : Number.NaN;
}

function sortableTime(value: string | null | undefined): number {
  const time = parseTime(value);
  return Number.isFinite(time) ? time : Number.NEGATIVE_INFINITY;
}

function isStoryCluster(value: unknown): value is StoryCluster {
  if (!value || typeof value !== "object") {
    return false;
  }

  const story = value as Partial<StoryCluster>;
  return typeof story.cluster_id === "string" && story.cluster_id.trim().length > 0 && typeof story.headline === "string";
}

function isFollowedStoryRecord(value: unknown): value is FollowedStoryRecord {
  if (!value || typeof value !== "object") {
    return false;
  }

  const record = value as Partial<FollowedStoryRecord>;
  return (
    typeof record.cluster_id === "string" &&
    record.cluster_id.trim().length > 0 &&
    typeof record.followed_at === "string" &&
    (typeof record.last_viewed_at === "string" || record.last_viewed_at === null) &&
    isStoryCluster(record.story) &&
    record.story.cluster_id === record.cluster_id
  );
}

export function sortFollowedStories(records: FollowedStoryRecord[]): FollowedStoryRecord[] {
  return [...records].sort((left, right) => {
    const unreadDiff = Number(isStoryUnread(right)) - Number(isStoryUnread(left));
    if (unreadDiff !== 0) {
      return unreadDiff;
    }

    const updatedDiff = sortableTime(right.story.last_updated) - sortableTime(left.story.last_updated);
    if (updatedDiff !== 0) {
      return updatedDiff;
    }

    const followedDiff = sortableTime(right.followed_at) - sortableTime(left.followed_at);
    if (followedDiff !== 0) {
      return followedDiff;
    }

    return left.cluster_id.localeCompare(right.cluster_id);
  });
}

export function parseFollowedStories(raw: string | null): FollowedStoryRecord[] {
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return sortFollowedStories(parsed.filter(isFollowedStoryRecord));
  } catch {
    return [];
  }
}

function getLocalStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readFollowedStories(storage = getLocalStorage()): FollowedStoryRecord[] {
  if (!storage) {
    return [];
  }

  try {
    return parseFollowedStories(storage.getItem(FOLLOWED_STORIES_STORAGE_KEY));
  } catch {
    return [];
  }
}

export function writeFollowedStories(records: FollowedStoryRecord[], storage = getLocalStorage()): void {
  if (!storage) {
    return;
  }

  try {
    storage.setItem(FOLLOWED_STORIES_STORAGE_KEY, JSON.stringify(sortFollowedStories(records)));
  } catch {
    // Browser storage can be disabled or full; keep the UI usable with in-memory state.
  }
}

export function followStorySnapshot(
  records: FollowedStoryRecord[],
  story: StoryCluster,
  followedAt = new Date().toISOString()
): FollowedStoryRecord[] {
  const existing = records.find((record) => record.cluster_id === story.cluster_id);
  const nextRecord: FollowedStoryRecord = {
    cluster_id: story.cluster_id,
    followed_at: existing?.followed_at ?? followedAt,
    last_viewed_at: existing?.last_viewed_at ?? story.last_updated ?? null,
    story
  };

  return sortFollowedStories([nextRecord, ...records.filter((record) => record.cluster_id !== story.cluster_id)]);
}

export function updateFollowedStorySnapshot(records: FollowedStoryRecord[], story: StoryCluster): FollowedStoryRecord[] {
  const existing = records.find((record) => record.cluster_id === story.cluster_id);
  if (!existing) {
    return sortFollowedStories(records);
  }

  return sortFollowedStories([
    {
      ...existing,
      story
    },
    ...records.filter((record) => record.cluster_id !== story.cluster_id)
  ]);
}

export function markFollowedStoryViewed(records: FollowedStoryRecord[], story: StoryCluster): FollowedStoryRecord[] {
  const existing = records.find((record) => record.cluster_id === story.cluster_id);
  if (!existing) {
    return sortFollowedStories(records);
  }

  return sortFollowedStories([
    {
      ...existing,
      last_viewed_at: story.last_updated ?? existing.last_viewed_at,
      story
    },
    ...records.filter((record) => record.cluster_id !== story.cluster_id)
  ]);
}

export function removeFollowedStory(records: FollowedStoryRecord[], clusterId: string): FollowedStoryRecord[] {
  return sortFollowedStories(records.filter((record) => record.cluster_id !== clusterId));
}

export function isStoryUnread(record: FollowedStoryRecord): boolean {
  const updatedAt = parseTime(record.story.last_updated);
  const viewedAt = parseTime(record.last_viewed_at);
  return Number.isFinite(updatedAt) && Number.isFinite(viewedAt) && updatedAt > viewedAt;
}

export function getUnreadFollowedCount(records: FollowedStoryRecord[]): number {
  return records.filter(isStoryUnread).length;
}

export function formatUnreadCount(count: number): string {
  return count > 9 ? "9+" : String(count);
}
