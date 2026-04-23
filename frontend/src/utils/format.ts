export function formatTimestamp(value: string | number | null): string {
  if (value === null || value === undefined) {
    return "(missing)";
  }

  let date: Date;
  if (typeof value === "number") {
    date = new Date(value * 1000);
  } else {
    date = new Date(value);
  }

  if (Number.isNaN(date.getTime())) {
    return "(invalid timestamp)";
  }

  return date.toISOString().replace("T", " ").replace(".000Z", " UTC");
}

export function formatScore(score: number): string {
  if (!Number.isFinite(score)) {
    return "(invalid)";
  }
  return score.toFixed(3);
}
