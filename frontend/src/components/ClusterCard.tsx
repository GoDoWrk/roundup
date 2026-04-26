import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { useSavedStories } from "../context/SavedStoriesContext";
import { useUserPreferences } from "../context/UserPreferencesContext";
import type { StoryCluster } from "../types";
import { formatReadableTimestamp, formatRelativeTime } from "../utils/format";
import {
  getClusterImageUrl,
  getFreshnessLabel,
  getUpdateCount,
  isRecentlyUpdated,
  previewSummary
} from "../utils/homepage";

interface ClusterCardProps {
  cluster: StoryCluster;
  to?: string;
  highlighted?: boolean;
  variant?: "standard" | "lead" | "supporting" | "thumbnail";
}

export function ClusterCard({ cluster, to, highlighted = false, variant = "standard" }: ClusterCardProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const { isSaved, toggleSaved } = useSavedStories();
  const { preferences } = useUserPreferences();
  const now = Date.now();
  const sourceCount = cluster.source_count ?? cluster.sources?.length ?? 0;
  const updateCount = getUpdateCount(cluster);
  const summary = cluster.summary?.trim() ?? "";
  const freshnessLabel = getFreshnessLabel(cluster.last_updated, now);
  const recentlyUpdated = isRecentlyUpdated(cluster.last_updated, now);
  const scoreLabel = Number.isFinite(cluster.score) ? cluster.score.toFixed(2) : null;
  const readableTimestamp = formatReadableTimestamp(cluster.last_updated);
  const relativeLabel = formatRelativeTime(cluster.last_updated, now);
  const hasValidTimestamp = readableTimestamp && !relativeLabel.startsWith("(");
  const className = `story-card story-card--${variant}${recentlyUpdated ? " story-card--fresh" : ""}${highlighted ? " story-card--updated" : ""}${to ? " story-card--linked" : ""}`;
  const imageUrl = getClusterImageUrl(cluster) ?? "";
  const showImage = imageUrl.length > 0 && !imageFailed;
  const topic = cluster.topic?.trim();
  const saved = isSaved(cluster.cluster_id);
  const saveLabel = saved ? `Remove saved story: ${cluster.headline}` : `Save story: ${cluster.headline}`;
  const shouldShowSummary = Boolean(summary) && variant !== "thumbnail" && (preferences.showSummaries || variant === "lead");

  useEffect(() => {
    setImageFailed(false);
  }, [imageUrl]);

  const content = (
    <>
      <div className={`story-card__image-frame${showImage ? "" : " story-card__image-frame--placeholder"}`}>
        {showImage ? (
          <img src={imageUrl} alt="" className="story-card__image" loading="lazy" onError={() => setImageFailed(true)} />
        ) : (
          <span aria-hidden="true">{topic?.slice(0, 1).toUpperCase() || "R"}</span>
        )}
      </div>
      <div className="story-card__eyebrow">
        {topic && <span className="story-card__topic">{topic}</span>}
        <span className="story-card__meta-count">
          {sourceCount} source{sourceCount === 1 ? "" : "s"}
        </span>
        <span className="story-card__meta-count">
          {updateCount} update{updateCount === 1 ? "" : "s"}
        </span>
        {freshnessLabel && recentlyUpdated && <span className="story-card__freshness">{freshnessLabel}</span>}
        {highlighted && <span className="story-card__refresh-badge">Updated since last refresh</span>}
      </div>
      <div className="story-card__title-row">
        <h3 className="story-card__headline">{cluster.headline}</h3>
        {scoreLabel && <span className="story-card__score">{scoreLabel}</span>}
      </div>
      {shouldShowSummary && (
        <p className="story-card__summary">{previewSummary(summary, variant === "supporting" ? 96 : undefined)}</p>
      )}
      {hasValidTimestamp && (
        <div className="story-card__footer">
          <span>{relativeLabel}</span>
          <span className="story-card__relative">{readableTimestamp}</span>
        </div>
      )}
    </>
  );

  return (
    <article className={className} data-testid="story-card" data-card-variant={variant}>
      {to ? (
        <Link to={to} className="story-card__link">
          {content}
        </Link>
      ) : (
        content
      )}
      <button
        type="button"
        className={`story-card__save-button${saved ? " story-card__save-button--saved" : ""}`}
        aria-label={saveLabel}
        aria-pressed={saved}
        onClick={() => toggleSaved(cluster)}
      >
        {saved ? "Saved" : "Save"}
      </button>
    </article>
  );
}
