import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchClusterDetail } from "../api/client";
import { useSavedStories } from "../context/SavedStoriesContext";
import type { SavedStoryRecord } from "../utils/savedStories";
import { formatReadableTimestamp, formatRelativeTime } from "../utils/format";
import { getClusterImageUrl, getUpdateCount } from "../utils/homepage";

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
  const imageUrl = getClusterImageUrl(story);
  const topic = story.topic?.trim();
  const sourceCount = story.source_count ?? story.sources?.length ?? 0;
  const updateCount = getUpdateCount(story);
  const savedAt = formatReadableTimestamp(record.saved_at) ?? "recently";
  const updatedRelative = formatRelativeTime(story.last_updated);
  const updatedReadable = formatReadableTimestamp(story.last_updated);
  const updatedLabel =
    updatedReadable && !updatedRelative.startsWith("(") ? `${updatedRelative} | ${updatedReadable}` : updatedReadable;

  return (
    <li className={`saved-story-row${missing ? " saved-story-row--missing" : ""}`}>
      <div className={`saved-story-row__image${imageUrl ? "" : " saved-story-row__image--placeholder"}`}>
        {imageUrl ? <img src={imageUrl} alt="" loading="lazy" /> : <span aria-hidden="true">{topic?.[0]?.toUpperCase() || "R"}</span>}
      </div>

      <div className="saved-story-row__copy">
        {missing && <span className="saved-story-row__status">No longer in live feed</span>}
        {missing ? (
          <h2>{story.headline}</h2>
        ) : (
          <Link to={`/story/${record.cluster_id}`} className="saved-story-row__title">
            {story.headline}
          </Link>
        )}
        <div className="saved-story-row__meta">
          {topic && <span>{topic}</span>}
          <span>
            {sourceCount} source{sourceCount === 1 ? "" : "s"}
          </span>
          <span>
            {updateCount} update{updateCount === 1 ? "" : "s"}
          </span>
          {updatedLabel && <span>Updated {updatedLabel}</span>}
          <span>Saved {savedAt}</span>
        </div>
      </div>

      <button type="button" className="saved-story-row__remove" onClick={onRemove} aria-label={`Remove saved story: ${story.headline}`}>
        Remove
      </button>
    </li>
  );
}

export function SavedStoriesPage() {
  const { savedStories, savedCount, saveStory, unsaveStory } = useSavedStories();
  const [missingIds, setMissingIds] = useState<Set<string>>(new Set());
  const [refreshFailed, setRefreshFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function refreshSavedStories() {
      if (savedStories.length === 0) {
        setMissingIds(new Set());
        setRefreshFailed(false);
        return;
      }

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
            {savedCount} saved {savedCount === 1 ? "story" : "stories"}
          </span>
          <span>Newest first</span>
        </div>
      </header>

      {refreshFailed && savedCount > 0 && (
        <div className="banner banner--warning" role="status">
          Live refresh failed for one or more saved stories. Showing saved local copies.
        </div>
      )}

      {savedCount === 0 ? (
        <section className="state-panel saved-page__empty">
          <p className="eyebrow">No saved stories</p>
          <h2>Your saved list is empty</h2>
          <p>Save stories from the homepage or story detail pages to build a local reading list in this browser.</p>
          <Link className="primary-button" to="/">
            Browse top stories
          </Link>
        </section>
      ) : (
        <section className="saved-story-list-panel" aria-labelledby="saved-story-list-heading">
          <div className="dashboard-section__header">
            <h2 id="saved-story-list-heading">Saved list</h2>
            <p>Stored locally in this browser.</p>
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
