import type { StoryCluster } from "../types";

export const SAVED_STORIES_STORAGE_KEY = "roundup-saved-stories-v1";

export interface SavedStoryRecord {
  cluster_id: string;
  saved_at: string;
  story: StoryCluster;
}

function parseTime(value: string): number {
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : Number.NEGATIVE_INFINITY;
}

function isStoryCluster(value: unknown): value is StoryCluster {
  if (!value || typeof value !== "object") {
    return false;
  }

  const story = value as Partial<StoryCluster>;
  return typeof story.cluster_id === "string" && story.cluster_id.trim().length > 0 && typeof story.headline === "string";
}

function isSavedStoryRecord(value: unknown): value is SavedStoryRecord {
  if (!value || typeof value !== "object") {
    return false;
  }

  const record = value as Partial<SavedStoryRecord>;
  return (
    typeof record.cluster_id === "string" &&
    record.cluster_id.trim().length > 0 &&
    typeof record.saved_at === "string" &&
    isStoryCluster(record.story) &&
    record.story.cluster_id === record.cluster_id
  );
}

export function sortSavedStories(records: SavedStoryRecord[]): SavedStoryRecord[] {
  return [...records].sort((left, right) => {
    const savedDiff = parseTime(right.saved_at) - parseTime(left.saved_at);
    if (savedDiff !== 0) {
      return savedDiff;
    }

    return left.cluster_id.localeCompare(right.cluster_id);
  });
}

export function parseSavedStories(raw: string | null): SavedStoryRecord[] {
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return sortSavedStories(parsed.filter(isSavedStoryRecord));
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

export function readSavedStories(storage = getLocalStorage()): SavedStoryRecord[] {
  if (!storage) {
    return [];
  }

  try {
    return parseSavedStories(storage.getItem(SAVED_STORIES_STORAGE_KEY));
  } catch {
    return [];
  }
}

export function writeSavedStories(records: SavedStoryRecord[], storage = getLocalStorage()): void {
  if (!storage) {
    return;
  }

  try {
    storage.setItem(SAVED_STORIES_STORAGE_KEY, JSON.stringify(sortSavedStories(records)));
  } catch {
    // Browser storage can be disabled or full; keep the UI usable with in-memory state.
  }
}

export function saveStorySnapshot(
  records: SavedStoryRecord[],
  story: StoryCluster,
  savedAt = new Date().toISOString()
): SavedStoryRecord[] {
  const existing = records.find((record) => record.cluster_id === story.cluster_id);
  const nextRecord: SavedStoryRecord = {
    cluster_id: story.cluster_id,
    saved_at: existing?.saved_at ?? savedAt,
    story
  };

  return sortSavedStories([
    nextRecord,
    ...records.filter((record) => record.cluster_id !== story.cluster_id)
  ]);
}

export function removeSavedStory(records: SavedStoryRecord[], clusterId: string): SavedStoryRecord[] {
  return sortSavedStories(records.filter((record) => record.cluster_id !== clusterId));
}
