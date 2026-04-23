import type { ParsedMetrics } from "../types";

const REQUIRED_KEYS: (keyof ParsedMetrics)[] = [
  "articles_ingested_total",
  "articles_deduplicated_total",
  "clusters_created_total",
  "clusters_updated_total",
  "last_ingest_time",
  "last_cluster_time"
];

export function parsePrometheusMetrics(raw: string): ParsedMetrics {
  const result: ParsedMetrics = {
    articles_ingested_total: null,
    articles_deduplicated_total: null,
    clusters_created_total: null,
    clusters_updated_total: null,
    last_ingest_time: null,
    last_cluster_time: null
  };

  const lines = raw.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const [key, value] = trimmed.split(/\s+/, 2);
    if (!key || value === undefined) {
      continue;
    }

    if (REQUIRED_KEYS.includes(key as keyof ParsedMetrics)) {
      const parsed = Number(value);
      result[key as keyof ParsedMetrics] = Number.isFinite(parsed) ? parsed : null;
    }
  }

  return result;
}
