import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchClusterDetail } from "../api/client";
import { StoryCard } from "../components/StoryCard";
import { useSavedStories } from "../context/SavedStoriesContext";
import type { SavedStoryRecord } from "../utils/savedStories";
import { formatReadableTimestamp } from "../utils/format";

function storiesAreEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function SavedStoryRow({
  record,
  missing,
  onRemove
}: {
  record: SavedStoryRecord;
  missing: boolean;
  onRemove: () => void;
}) {
  const story = record.story;
  const savedAt = formatReadableTimestamp(record.saved_at) ?? "recently";

  return (
    <li className={`saved-story-list__item${missing ? " saved-story-list__item--missing" : ""}`}>
      <StoryCard
        cluster={story}
        to={missing ? undefined : `/story/${record.cluster_id}`}
        variant="saved"
        statusLabel={missing ? "No longer in live feed" : undefined}
        savedAtLabel={savedAt}
        action={{
          label: `Remove saved story: ${story.headline}`,
          text: "Remove",
          onClick: onRemove
        }}
      />
    </li>
  );
}

function SavedStorySkeleton() {
  return (
    <article className="story-card story-card--saved story-card--skeleton" aria-hidden="true">
      <div className="story-card__image-frame" />
      <div className="story-card__content">
        <div className="story-card__eyebrow">
          <span className="story-skeleton story-skeleton--pill" />
          <span className="story-skeleton story-skeleton--line story-skeleton--tiny" />
        </div>
        <div className="story-skeleton story-skeleton--headline" />
        <div className="story-skeleton story-skeleton--line" />
        <div className="story-skeleton story-skeleton--line story-skeleton--short" />
      </div>
    </article>
  );
}

export function SavedStoriesPage() {
  const { savedStories, savedCount, saveStory, unsaveStory } = useSavedStories();
  const [missingIds, setMissingIds] = useState<Set<string>>(new Set());
  const [refreshFailed, setRefreshFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function refreshSavedStories() {
      if (savedStories.length === 0) {
        setMissingIds(new Set());
        setRefreshFailed(false);
        setRefreshing(false);
        return;
      }

      setRefreshing(true);
      const missing = new Set<string>();
      let hadRefreshError = false;

      await Promise.all(
        savedStories.map(async (record) => {
          try {
            const freshStory = await fetchClusterDetail(record.cluster_id);
            if (!freshStory) {
              missing.add(record.cluster_id);
              return;
            }

            if (!storiesAreEqual(freshStory, record.story)) {
              saveStory(freshStory);
            }
          } catch {
            hadRefreshError = true;
          }
        })
      );

      if (!cancelled) {
        setMissingIds(missing);
        setRefreshFailed(hadRefreshError);
        setRefreshing(false);
      }
    }

    void refreshSavedStories();
    return () => {
      cancelled = true;
    };
  }, [saveStory, savedStories]);

  return (
    <div className="public-page saved-page">
      <header className="public-hero saved-page__header">
        <div className="public-hero__copy">
          <p className="eyebrow">Library</p>
          <h1>Saved Stories</h1>
          <p>Stories saved in this browser, kept locally without accounts or backend changes.</p>
        </div>
        <div className="public-hero__meta" aria-live="polite">
          <span>
            <strong>Saved locally</strong>
            {savedCount} saved {savedCount === 1 ? "story" : "stories"}
          </span>
          <span>
            <strong>Storage</strong>
            This browser only
          </span>
          <span>
            <strong>Order</strong>
            Newest first
          </span>
        </div>
      </header>

      {refreshing && savedCount > 0 && (
        <div className="saved-story-refresh" aria-busy="true" role="status">
          <span>Refreshing saved story snapshots from the live API...</span>
          <div className="saved-story-refresh__skeletons">
            <SavedStorySkeleton />
          </div>
        </div>
      )}

      {refreshFailed && savedCount > 0 && (
        <div className="banner banner--warning" role="status">
          Could not refresh one or more saved stories. Showing the local browser copies so your saved list stays usable.
        </div>
      )}

      {savedCount === 0 ? (
        <section className="state-panel saved-page__empty">
          <p className="eyebrow">No saved stories</p>
          <h2>Your saved list is empty</h2>
          <p>
            Save stories from the homepage or story detail pages to build a local reading list. Saved stories are stored
            in this browser until account sync is added.
          </p>
          <Link className="primary-button" to="/">
            Browse top stories
          </Link>
        </section>
      ) : (
        <section className="saved-story-list-panel" aria-labelledby="saved-story-list-heading">
          <div className="dashboard-section__header">
            <h2 id="saved-story-list-heading">Saved list</h2>
            <p>Readable snapshots with live details refreshed when available.</p>
          </div>
          <ul className="saved-story-list">
            {savedStories.map((record) => (
              <SavedStoryRow
                key={record.cluster_id}
                record={record}
                missing={missingIds.has(record.cluster_id)}
                onRemove={() => unsaveStory(record.cluster_id)}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
