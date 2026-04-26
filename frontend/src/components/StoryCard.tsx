import { Link } from "react-router-dom";
import { useEffect, type MouseEvent } from "react";
import { ImageWithFallback } from "./ImageWithFallback";
import { useFollowedStories } from "../context/FollowedStoriesContext";
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

export type StoryCardVariant =
  | "featured"
  | "standard"
  | "compact"
  | "saved"
  | "timeline"
  | "lead"
  | "supporting"
  | "thumbnail";

interface StoryCardAction {
  label: string;
  text: string;
  onClick: () => void;
  pressed?: boolean;
}

export interface StoryCardProps {
  cluster: StoryCluster;
  to?: string;
  highlighted?: boolean;
  variant?: StoryCardVariant;
  statusLabel?: string;
  savedAtLabel?: string;
  action?: StoryCardAction;
}

function normalizeVariant(variant: StoryCardVariant): "featured" | "standard" | "compact" | "saved" | "timeline" {
  if (variant === "lead") {
    return "featured";
  }

  if (variant === "supporting" || variant === "thumbnail") {
    return "compact";
  }

  return variant;
}

function metricLabel(label: string, value: number): string | null {
  return Number.isFinite(value) ? `${label} ${value.toFixed(2)}` : null;
}

function safeCount(value: number | null | undefined, fallback = 0): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return fallback;
  }

  return value;
}

export function StoryCard({
  cluster,
  to,
  highlighted = false,
  variant = "standard",
  statusLabel,
  savedAtLabel,
  action
}: StoryCardProps) {
  const { isSaved, toggleSaved } = useSavedStories();
  const { isFollowed, updateFollowedStory } = useFollowedStories();
  const { preferences } = useUserPreferences();
  const normalizedVariant = normalizeVariant(variant);
  const now = Date.now();
  const headline = cluster.headline?.trim() || "Untitled story";
  const sourceCount = safeCount(cluster.source_count, cluster.sources?.length ?? 0);
  const updateCount = getUpdateCount(cluster);
  const summary = cluster.summary?.trim() ?? "";
  const topic = cluster.topic?.trim();
  const lastUpdated = cluster.last_updated ?? null;
  const freshnessLabel = lastUpdated ? getFreshnessLabel(lastUpdated, now) : null;
  const recentlyUpdated = lastUpdated ? isRecentlyUpdated(lastUpdated, now) : false;
  const relevanceLabel = metricLabel("Relevance", cluster.score);
  const confidenceLabel = metricLabel("Confidence", cluster.confidence_score);
  const readableTimestamp = formatReadableTimestamp(lastUpdated);
  const relativeLabel = formatRelativeTime(lastUpdated, now);
  const hasValidTimestamp = readableTimestamp && !relativeLabel.startsWith("(");
  const imageUrl = getClusterImageUrl(cluster) ?? "";
  const saved = isSaved(cluster.cluster_id);
  const saveLabel = saved ? `Remove saved story: ${headline}` : `Save story: ${headline}`;
  const shouldShowSummary =
    Boolean(summary) &&
    normalizedVariant !== "timeline" &&
    (preferences.showSummaries || normalizedVariant === "featured" || normalizedVariant === "saved");
  const className = [
    "story-card",
    `story-card--${normalizedVariant}`,
    recentlyUpdated ? "story-card--fresh" : "",
    highlighted ? "story-card--updated" : "",
    to ? "story-card--linked" : "",
    statusLabel ? "story-card--has-status" : ""
  ]
    .filter(Boolean)
    .join(" ");
  const primaryAction =
    action ??
    ({
      label: saveLabel,
      text: saved ? "Saved" : "Save",
      pressed: saved,
      onClick: () => toggleSaved(cluster)
    } satisfies StoryCardAction);

  useEffect(() => {
    if (isFollowed(cluster.cluster_id)) {
      updateFollowedStory(cluster);
    }
  }, [cluster, isFollowed, updateFollowedStory]);

  function handleActionClick(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    primaryAction.onClick();
  }

  const content = (
    <>
      <ImageWithFallback
        src={imageUrl}
        label={topic || headline}
        className="story-card__image-frame"
        imageClassName="story-card__image"
      />
      <div className="story-card__content">
        <div className="story-card__eyebrow">
          {statusLabel && <span className="story-card__status">{statusLabel}</span>}
          {topic && <span className="story-card__topic">{topic}</span>}
          <span className="story-card__meta-count">
            {sourceCount} source{sourceCount === 1 ? "" : "s"}
          </span>
          <span className="story-card__meta-count">
            {updateCount} update{updateCount === 1 ? "" : "s"}
          </span>
          {relevanceLabel && <span className="story-card__signal">{relevanceLabel}</span>}
          {confidenceLabel && <span className="story-card__signal">{confidenceLabel}</span>}
          {freshnessLabel && recentlyUpdated && <span className="story-card__freshness">{freshnessLabel}</span>}
          {highlighted && <span className="story-card__refresh-badge">Updated since last refresh</span>}
        </div>

        <div className="story-card__title-row">
          <h3 className="story-card__headline">{headline}</h3>
        </div>

        {shouldShowSummary && (
          <p className="story-card__summary">
            {previewSummary(summary, normalizedVariant === "compact" ? 112 : normalizedVariant === "saved" ? 150 : undefined)}
          </p>
        )}

        {normalizedVariant === "featured" && (
          <dl className="story-card__brief-grid" aria-label="Story signals">
            <div>
              <dt>Latest update</dt>
              <dd>{hasValidTimestamp ? relativeLabel : "No timestamp"}</dd>
            </div>
            <div>
              <dt>Coverage</dt>
              <dd>
                {sourceCount} source{sourceCount === 1 ? "" : "s"}
              </dd>
            </div>
            <div>
              <dt>Signal</dt>
              <dd>{confidenceLabel ?? relevanceLabel ?? "Pending"}</dd>
            </div>
          </dl>
        )}

        {(hasValidTimestamp || savedAtLabel) && (
          <div className="story-card__footer">
            {hasValidTimestamp && <span>Updated {relativeLabel}</span>}
            {hasValidTimestamp && <span className="story-card__relative">{readableTimestamp}</span>}
            {savedAtLabel && <span className="story-card__saved-at">Saved {savedAtLabel}</span>}
          </div>
        )}
      </div>
    </>
  );

  return (
    <article className={className} data-testid="story-card" data-card-variant={normalizedVariant}>
      {to ? (
        <Link to={to} className="story-card__link">
          {content}
        </Link>
      ) : (
        <div className="story-card__link story-card__link--static">{content}</div>
      )}
      <button
        type="button"
        className={`story-card__save-button${primaryAction.pressed ? " story-card__save-button--saved" : ""}`}
        aria-label={primaryAction.label}
        aria-pressed={primaryAction.pressed ?? false}
        onClick={handleActionClick}
      >
        {primaryAction.text}
      </button>
    </article>
  );
}
