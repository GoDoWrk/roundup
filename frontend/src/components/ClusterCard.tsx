import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import type { StoryCluster } from "../types";
import { formatReadableTimestamp, formatRelativeTime } from "../utils/format";
import { getFreshnessLabel, isRecentlyUpdated, previewSummary } from "../utils/homepage";

interface ClusterCardProps {
  cluster: StoryCluster;
  to?: string;
  highlighted?: boolean;
}

export function ClusterCard({ cluster, to, highlighted = false }: ClusterCardProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const now = Date.now();
  const sourceCount = cluster.sources.length;
  const summary = cluster.summary.trim();
  const freshnessLabel = getFreshnessLabel(cluster.last_updated, now);
  const recentlyUpdated = isRecentlyUpdated(cluster.last_updated, now);
  const scoreLabel = Number.isFinite(cluster.score) ? cluster.score.toFixed(2) : null;
  const readableTimestamp = formatReadableTimestamp(cluster.last_updated);
  const relativeLabel = formatRelativeTime(cluster.last_updated, now);
  const hasValidTimestamp = readableTimestamp && !relativeLabel.startsWith("(");
  const className = `story-card${recentlyUpdated ? " story-card--fresh" : ""}${highlighted ? " story-card--updated" : ""}${to ? " story-card--linked" : ""}`;
  const imageUrl = cluster.primary_image_url?.trim() || "";
  const showImage = imageUrl.length > 0 && !imageFailed;

  useEffect(() => {
    setImageFailed(false);
  }, [imageUrl]);

  const content = (
    <>
      {showImage && (
        <div className="story-card__image-frame">
          <img src={imageUrl} alt="" className="story-card__image" loading="lazy" onError={() => setImageFailed(true)} />
        </div>
      )}
      <div className="story-card__eyebrow">
        <span className="story-card__source-count">
          {sourceCount} source{sourceCount === 1 ? "" : "s"}
        </span>
        {freshnessLabel && recentlyUpdated && <span className="story-card__freshness">{freshnessLabel}</span>}
        {highlighted && <span className="story-card__refresh-badge">Updated since last refresh</span>}
      </div>
      <div className="story-card__title-row">
        <h3 className="story-card__headline">{cluster.headline}</h3>
        {scoreLabel && <span className="story-card__score">{scoreLabel}</span>}
      </div>
      {summary && <p className="story-card__summary">{previewSummary(summary)}</p>}
      {hasValidTimestamp && (
        <div className="story-card__footer">
          <span>{relativeLabel}</span>
          <span className="story-card__relative">{readableTimestamp}</span>
        </div>
      )}
    </>
  );

  if (to) {
    return (
      <Link to={to} className={className} data-testid="story-card">
        {content}
      </Link>
    );
  }

  return (
    <article className={className} data-testid="story-card">
      {content}
    </article>
  );
}
