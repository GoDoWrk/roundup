export interface TimelineEvent {
  timestamp: string;
  event: string;
  source_url: string;
  source_title: string;
}

export interface SourceReference {
  article_id: number;
  title: string;
  url: string;
  publisher: string;
  published_at: string;
}

export interface StoryCluster {
  cluster_id: string;
  headline: string;
  summary: string;
  what_changed: string;
  why_it_matters: string;
  timeline: TimelineEvent[];
  sources: SourceReference[];
  first_seen: string;
  last_updated: string;
  score: number;
  status: "emerging" | "active" | "stale";
}

export interface ClusterListResponse {
  total: number;
  limit: number;
  offset: number;
  items: StoryCluster[];
}

export interface ClusterDebugThresholds {
  score_threshold: number;
  title_signal_threshold: number;
  entity_overlap_threshold: number;
  keyword_overlap_threshold: number;
  min_sources_for_api: number;
}

export interface ClusterDebugScoreBreakdown {
  average_similarity_score: number;
  average_title_similarity: number;
  average_entity_jaccard: number;
  average_keyword_jaccard: number;
  average_time_proximity: number;
}

export interface ClusterDebugExplanation {
  grouping_reason: string;
  thresholds: ClusterDebugThresholds;
  threshold_results: Record<string, boolean>;
  top_shared_entities: string[];
  top_shared_keywords: string[];
  score_breakdown: ClusterDebugScoreBreakdown;
  decision_counts: Record<string, number>;
}

export interface ClusterDebugItem {
  cluster_id: string;
  status: string;
  score: number;
  source_count: number;
  visibility_threshold: number;
  promotion_eligible: boolean;
  promoted_at: string | null;
  previous_status: string | null;
  promotion_reason: string | null;
  promotion_explanation: string | null;
  validation_error: string | null;
  headline: string;
  summary: string;
  debug_explanation: ClusterDebugExplanation;
}

export interface ClusterDebugResponse {
  total: number;
  items: ClusterDebugItem[];
}

export interface ParsedMetrics {
  articles_ingested_total: number | null;
  articles_deduplicated_total: number | null;
  clusters_created_total: number | null;
  clusters_updated_total: number | null;
  clusters_promoted_total: number | null;
  clusters_hidden_total: number | null;
  clusters_active_total: number | null;
  cluster_promotion_attempts_total: number | null;
  cluster_promotion_failures_total: number | null;
  last_ingest_time: number | null;
  last_cluster_time: number | null;
}
