function toDate(value: string | number | null | undefined): Date | null {
  if (value === null || value === undefined) {
    return null;
  }

  const date = typeof value === "number" ? new Date(value > 1_000_000_000_000 ? value : value * 1000) : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatTimestamp(value: string | number | null): string {
  const date = toDate(value);
  if (!date) {
    return value === null || value === undefined ? "(missing)" : "(invalid timestamp)";
  }

  return date.toISOString().replace("T", " ").replace(".000Z", " UTC");
}

export function formatScore(score: number): string {
  if (!Number.isFinite(score)) {
    return "(invalid)";
  }
  return score.toFixed(3);
}

export function formatReadableTimestamp(value: string | number | null): string | null {
  const date = toDate(value);
  if (!date) {
    return null;
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(date);
}

export function formatRelativeTime(value: string | number | null, referenceTime = Date.now()): string {
  const date = toDate(value);
  if (!date) {
    return "(missing)";
  }

  const diffMs = referenceTime - date.getTime();
  const absMinutes = Math.floor(Math.abs(diffMs) / 60000);

  if (absMinutes < 1) {
    return "just now";
  }

  if (absMinutes < 60) {
    return diffMs >= 0 ? `${absMinutes}m ago` : `in ${absMinutes}m`;
  }

  const absHours = Math.floor(absMinutes / 60);
  if (absHours < 24) {
    return diffMs >= 0 ? `${absHours}h ago` : `in ${absHours}h`;
  }

  const absDays = Math.floor(absHours / 24);
  return diffMs >= 0 ? `${absDays}d ago` : `in ${absDays}d`;
}
