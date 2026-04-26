import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchClusterDetail } from "../api/client";
import { ImageWithFallback } from "../components/ImageWithFallback";
import { useFollowedStories } from "../context/FollowedStoriesContext";
import type { FollowedStoryRecord } from "../utils/followedStories";
import { isStoryUnread } from "../utils/followedStories";
import { formatReadableTimestamp, formatRelativeTime } from "../utils/format";
import { getClusterImageUrl, getUpdateCount } from "../utils/homepage";

function storiesAreEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function AlertStoryRow({
  record,
  missing,
  onUnfollow
}: {
  record: FollowedStoryRecord;
  missing: boolean;
  onUnfollow: () => void;
}) {
  const story = record.story;
  const imageUrl = getClusterImageUrl(story);
  const topic = story.topic?.trim();
  const sourceCount = story.source_count ?? story.sources?.length ?? 0;
  const updateCount = getUpdateCount(story);
  const followedAt = formatReadableTimestamp(record.followed_at) ?? "recently";
  const lastViewedAt = record.last_viewed_at ? formatReadableTimestamp(record.last_viewed_at) : null;
  const updatedRelative = formatRelativeTime(story.last_updated);
  const updatedReadable = formatReadableTimestamp(story.last_updated);
  const updatedLabel =
    updatedReadable && !updatedRelative.startsWith("(") ? `${updatedRelative} | ${updatedReadable}` : updatedReadable;
  const unread = isStoryUnread(record);

  return (
    <li className={`saved-story-row alert-story-row${missing ? " saved-story-row--missing" : ""}`}>
      <ImageWithFallback src={imageUrl} label={topic} className="saved-story-row__image" />

      <div className="saved-story-row__copy">
        {unread && <span className="saved-story-row__status alert-story-row__status--unread">New update</span>}
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
          {lastViewedAt && <span>Last viewed {lastViewedAt}</span>}
          <span>Followed {followedAt}</span>
        </div>
      </div>

      <button type="button" className="saved-story-row__remove" onClick={onUnfollow} aria-label={`Unfollow story: ${story.headline}`}>
        Unfollow
      </button>
    </li>
  );
}

export function AlertsPage() {
  const { followedStories, followedCount, unreadCount, updateFollowedStory, unfollowStory } = useFollowedStories();
  const [missingIds, setMissingIds] = useState<Set<string>>(new Set());
  const [refreshFailed, setRefreshFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function refreshFollowedStories() {
      if (followedStories.length === 0) {
        setMissingIds(new Set());
        setRefreshFailed(false);
        return;
      }

      const missing = new Set<string>();
      let hadRefreshError = false;

      await Promise.all(
        followedStories.map(async (record) => {
          try {
            const freshStory = await fetchClusterDetail(record.cluster_id);
            if (!freshStory) {
              missing.add(record.cluster_id);
              return;
            }

            if (!storiesAreEqual(freshStory, record.story)) {
              updateFollowedStory(freshStory);
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

    void refreshFollowedStories();
    return () => {
      cancelled = true;
    };
  }, [followedStories, updateFollowedStory]);

  return (
    <div className="public-page alerts-page">
      <header className="public-hero alerts-page__header">
        <div className="public-hero__copy">
          <p className="eyebrow">Alerts</p>
          <h1>Followed Stories</h1>
          <p>Story alerts tracked in this browser, using live Roundup updates without accounts, email, or push notifications.</p>
        </div>
        <div className="public-hero__meta" aria-live="polite">
          <span>
            {followedCount} followed {followedCount === 1 ? "story" : "stories"}
          </span>
          <span>
            {unreadCount} new {unreadCount === 1 ? "update" : "updates"}
          </span>
        </div>
      </header>

      {refreshFailed && followedCount > 0 && (
        <div className="banner banner--warning" role="status">
          Live refresh failed for one or more followed stories. Showing local copies.
        </div>
      )}

      {followedCount === 0 ? (
        <section className="state-panel alerts-page__empty">
          <p className="eyebrow">No followed stories</p>
          <h2>No alerts yet</h2>
          <p>
            Follow a story from its detail page to track future updates in this browser. Roundup will not send email,
            push notifications, or sync this list to an account.
          </p>
          <Link className="primary-button" to="/">
            Browse top stories
          </Link>
        </section>
      ) : (
        <section className="saved-story-list-panel alerts-story-list-panel" aria-labelledby="alerts-story-list-heading">
          <div className="dashboard-section__header">
            <h2 id="alerts-story-list-heading">Followed story alerts</h2>
            <p>Open a story to mark its latest update as viewed.</p>
          </div>
          <ul className="saved-story-list">
            {followedStories.map((record) => (
              <AlertStoryRow
                key={record.cluster_id}
                record={record}
                missing={missingIds.has(record.cluster_id)}
                onUnfollow={() => unfollowStory(record.cluster_id)}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
