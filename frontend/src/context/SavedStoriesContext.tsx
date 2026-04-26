import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { StoryCluster } from "../types";
import {
  readSavedStories,
  removeSavedStory,
  saveStorySnapshot,
  SAVED_STORIES_STORAGE_KEY,
  sortSavedStories,
  writeSavedStories,
  type SavedStoryRecord
} from "../utils/savedStories";

interface SavedStoriesContextValue {
  savedStories: SavedStoryRecord[];
  savedCount: number;
  isSaved: (clusterId: string) => boolean;
  saveStory: (story: StoryCluster) => void;
  unsaveStory: (clusterId: string) => void;
  toggleSaved: (story: StoryCluster) => void;
}

const SavedStoriesContext = createContext<SavedStoriesContextValue | null>(null);

export function SavedStoriesProvider({ children }: { children: ReactNode }) {
  const [savedStories, setSavedStories] = useState<SavedStoryRecord[]>(() => readSavedStories());

  useEffect(() => {
    function handleStorage(event: StorageEvent) {
      if (event.key === SAVED_STORIES_STORAGE_KEY) {
        setSavedStories(readSavedStories());
      }
    }

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const persist = useCallback((updater: (records: SavedStoryRecord[]) => SavedStoryRecord[]) => {
    setSavedStories((current) => {
      const next = sortSavedStories(updater(current));
      writeSavedStories(next);
      return next;
    });
  }, []);

  const isSaved = useCallback(
    (clusterId: string) => savedStories.some((record) => record.cluster_id === clusterId),
    [savedStories]
  );

  const saveStory = useCallback(
    (story: StoryCluster) => {
      persist((records) => saveStorySnapshot(records, story));
    },
    [persist]
  );

  const unsaveStory = useCallback(
    (clusterId: string) => {
      persist((records) => removeSavedStory(records, clusterId));
    },
    [persist]
  );

  const toggleSaved = useCallback(
    (story: StoryCluster) => {
      persist((records) =>
        records.some((record) => record.cluster_id === story.cluster_id)
          ? removeSavedStory(records, story.cluster_id)
          : saveStorySnapshot(records, story)
      );
    },
    [persist]
  );

  const value = useMemo(
    () => ({
      savedStories,
      savedCount: savedStories.length,
      isSaved,
      saveStory,
      unsaveStory,
      toggleSaved
    }),
    [isSaved, saveStory, savedStories, toggleSaved, unsaveStory]
  );

  return <SavedStoriesContext.Provider value={value}>{children}</SavedStoriesContext.Provider>;
}

export function useSavedStories() {
  const context = useContext(SavedStoriesContext);
  if (!context) {
    throw new Error("useSavedStories must be used within SavedStoriesProvider");
  }

  return context;
}
