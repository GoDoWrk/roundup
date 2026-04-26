import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { StoryCluster } from "../types";
import {
  FOLLOWED_STORIES_STORAGE_KEY,
  followStorySnapshot,
  getUnreadFollowedCount,
  markFollowedStoryViewed,
  readFollowedStories,
  removeFollowedStory,
  sortFollowedStories,
  updateFollowedStorySnapshot,
  writeFollowedStories,
  type FollowedStoryRecord
} from "../utils/followedStories";

interface FollowedStoriesContextValue {
  followedStories: FollowedStoryRecord[];
  followedCount: number;
  unreadCount: number;
  isFollowed: (clusterId: string) => boolean;
  followStory: (story: StoryCluster) => void;
  unfollowStory: (clusterId: string) => void;
  toggleFollowed: (story: StoryCluster) => void;
  updateFollowedStory: (story: StoryCluster) => void;
  markStoryViewed: (story: StoryCluster) => void;
}

const FollowedStoriesContext = createContext<FollowedStoriesContextValue | null>(null);

function recordsAreEqual(left: FollowedStoryRecord[], right: FollowedStoryRecord[]): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function FollowedStoriesProvider({ children }: { children: ReactNode }) {
  const [followedStories, setFollowedStories] = useState<FollowedStoryRecord[]>(() => readFollowedStories());

  useEffect(() => {
    function handleStorage(event: StorageEvent) {
      if (event.key === FOLLOWED_STORIES_STORAGE_KEY) {
        setFollowedStories(readFollowedStories());
      }
    }

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const persist = useCallback((updater: (records: FollowedStoryRecord[]) => FollowedStoryRecord[]) => {
    setFollowedStories((current) => {
      const next = sortFollowedStories(updater(current));
      if (recordsAreEqual(current, next)) {
        return current;
      }

      writeFollowedStories(next);
      return next;
    });
  }, []);

  const isFollowed = useCallback(
    (clusterId: string) => followedStories.some((record) => record.cluster_id === clusterId),
    [followedStories]
  );

  const followStory = useCallback(
    (story: StoryCluster) => {
      persist((records) => followStorySnapshot(records, story));
    },
    [persist]
  );

  const unfollowStory = useCallback(
    (clusterId: string) => {
      persist((records) => removeFollowedStory(records, clusterId));
    },
    [persist]
  );

  const toggleFollowed = useCallback(
    (story: StoryCluster) => {
      persist((records) =>
        records.some((record) => record.cluster_id === story.cluster_id)
          ? removeFollowedStory(records, story.cluster_id)
          : followStorySnapshot(records, story)
      );
    },
    [persist]
  );

  const updateFollowedStory = useCallback(
    (story: StoryCluster) => {
      persist((records) => updateFollowedStorySnapshot(records, story));
    },
    [persist]
  );

  const markStoryViewed = useCallback(
    (story: StoryCluster) => {
      persist((records) => markFollowedStoryViewed(records, story));
    },
    [persist]
  );

  const unreadCount = useMemo(() => getUnreadFollowedCount(followedStories), [followedStories]);

  const value = useMemo(
    () => ({
      followedStories,
      followedCount: followedStories.length,
      unreadCount,
      isFollowed,
      followStory,
      unfollowStory,
      toggleFollowed,
      updateFollowedStory,
      markStoryViewed
    }),
    [followStory, followedStories, isFollowed, markStoryViewed, toggleFollowed, unfollowStory, unreadCount, updateFollowedStory]
  );

  return <FollowedStoriesContext.Provider value={value}>{children}</FollowedStoriesContext.Provider>;
}

export function useFollowedStories() {
  const context = useContext(FollowedStoriesContext);
  if (!context) {
    throw new Error("useFollowedStories must be used within FollowedStoriesProvider");
  }

  return context;
}
