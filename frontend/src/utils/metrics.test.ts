import { describe, expect, it } from "vitest";
import { parsePrometheusMetrics } from "./metrics";

describe("parsePrometheusMetrics", () => {
  it("parses required metrics", () => {
    const raw = `
# HELP articles_ingested_total x
articles_ingested_total 12
articles_deduplicated_total 2
clusters_created_total 4
clusters_updated_total 5
clusters_promoted_total 2
clusters_hidden_total 11
clusters_active_total 8
cluster_promotion_attempts_total 7
cluster_promotion_failures_total 3
last_ingest_time 1713000000
last_cluster_time 1713000200
`;

    const parsed = parsePrometheusMetrics(raw);
    expect(parsed.articles_ingested_total).toBe(12);
    expect(parsed.articles_deduplicated_total).toBe(2);
    expect(parsed.clusters_created_total).toBe(4);
    expect(parsed.clusters_updated_total).toBe(5);
    expect(parsed.clusters_promoted_total).toBe(2);
    expect(parsed.clusters_hidden_total).toBe(11);
    expect(parsed.clusters_active_total).toBe(8);
    expect(parsed.cluster_promotion_attempts_total).toBe(7);
    expect(parsed.cluster_promotion_failures_total).toBe(3);
    expect(parsed.last_ingest_time).toBe(1713000000);
    expect(parsed.last_cluster_time).toBe(1713000200);
  });

  it("returns null for missing values", () => {
    const parsed = parsePrometheusMetrics("articles_ingested_total 1");
    expect(parsed.articles_ingested_total).toBe(1);
    expect(parsed.clusters_updated_total).toBeNull();
    expect(parsed.clusters_promoted_total).toBeNull();
    expect(parsed.last_cluster_time).toBeNull();
  });
});
