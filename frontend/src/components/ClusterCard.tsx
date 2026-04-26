import { Link } from "react-router-dom";
import { ImageWithFallback } from "./ImageWithFallback";
import { useSavedStories } from "../context/SavedStoriesContext";
import { useUserPreferences } from "../context/UserPreferencesContext";
import type { StoryCluster } from "../types";
import { formatReadableTimestamp, formatRelativeTime } from "../utils/format";
import {
  getClusterImageUrl,
  getUpdateCount,
  isRecentlyUpdated,
  previewSummary,
  readerText
} from "../utils/homepage";

interface ClusterCardProps {
  cluster: StoryCluster;
  to?: string;
  highlighted?: boolean;
  variant?: "standard" | "lead" | "supporting" | "thumbnail";
}

export function ClusterCard({ cluster, to, highlighted = false, variant = "standard" }: ClusterCardProps) {
  const { isSaved, toggleSaved } = useSavedStories();
  const { preferences } = useUserPreferences();
  const now = Date.now();
  const sourceCount = cluster.source_count ?? cluster.sources?.length ?? 0;
  const updateCount = getUpdateCount(cluster);
  const summary = readerText(cluster.summary) ?? "";
  const recentlyUpdated = isRecentlyUpdated(cluster.last_updated, now);
  const isCandidate = cluster.visibility === "candidate" || cluster.status === "hidden";
  const readableTimestamp = formatReadableTimestamp(cluster.last_updated);
  const relativeLabel = formatRelativeTime(cluster.last_updated, now);
  const hasValidTimestamp = readableTimestamp && !relativeLabel.startsWith("(");
  const className = `story-card story-card--${variant}${recentlyUpdated ? " story-card--fresh" : ""}${highlighted ? " story-card--updated" : ""}${to ? " story-card--linked" : ""}`;
  const imageUrl = getClusterImageUrl(cluster) ?? "";
  const topic = cluster.topic?.trim();
  const saved = isSaved(cluster.cluster_id);
  const saveLabel = saved ? `Remove saved story: ${cluster.headline}` : `Save story: ${cluster.headline}`;
  const shouldShowSummary = Boolean(summary) && variant !== "thumbnail" && (preferences.showSummaries || variant === "lead");
  const sourceLabel =
    sourceCount > 0 ? `${sourceCount} source${sourceCount === 1 ? "" : "s"}` : "Sources pending";
  const updateLabel =
    updateCount > 0 ? `${updateCount} update${updateCount === 1 ? "" : "s"}` : "No updates yet";
  const statusLabels = [
    sourceCount === 1 || cluster.is_single_source ? "Single source" : null,
    sourceCount !== 1 && cluster.is_developing ? "Developing" : null,
    sourceCount !== 1 && !cluster.is_developing && isCandidate ? "Developing" : null,
    recentlyUpdated ? "Updated recently" : null,
    highlighted ? "Updated" : null
  ].filter((label): label is string => Boolean(label));

  const content = (
    <>
      <ImageWithFallback
        src={imageUrl}
        label={topic}
        className="story-card__image-frame"
        imageClassName="story-card__image"
      />
      <div className="story-card__eyebrow">
        {topic && <span className="story-card__topic">{topic}</span>}
        <span className="story-card__meta-count">{sourceLabel}</span>
        <span className="story-card__meta-count">{updateLabel}</span>
        {statusLabels.map((label) => (
          <span
            key={label}
            className={`story-card__status${label === "Single source" || isCandidate ? " story-card__status--candidate" : ""}`}
          >
            {label}
          </span>
        ))}
      </div>
      <div className="story-card__title-row">
        <h3 className="story-card__headline">{cluster.headline}</h3>
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
