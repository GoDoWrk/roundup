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
  image_url?: string | null;
}

export interface StoryCluster {
  cluster_id: string;
  headline: string;
  topic: string;
  summary: string;
  what_changed: string;
  why_it_matters: string;
  key_facts: string[];
  timeline: TimelineEvent[];
  timeline_events: TimelineEvent[];
  sources: SourceReference[];
  source_count: number;
  primary_image_url: string | null;
  thumbnail_urls: string[];
  region: string | null;
  story_type: string;
  first_seen: string;
  last_updated: string;
  is_developing: boolean;
  is_breaking: boolean;
  confidence_score: number;
  related_cluster_ids: string[];
  score: number;
  status: "emerging" | "active" | "stale";
}

export interface ClusterListResponse {
  total: number;
  limit: number;
  offset: number;
  items: StoryCluster[];
}

export type SearchResultType = "cluster" | "update" | "source";

export interface SearchCounts {
  all: number;
  clusters: number;
  updates: number;
  sources: number;
}

export interface SearchResult {
  id: string;
  type: SearchResultType;
  cluster_id: string;
  title: string;
  snippet: string;
  topic: string;
  thumbnail_url: string | null;
  source_name: string | null;
  source_count: number;
  update_count: number;
  last_updated: string;
  article_url?: string | null;
  published_at?: string | null;
  matched_field?: string | null;
}

export interface SearchResponse {
  query: string;
  total: number;
  limit: number;
  counts: SearchCounts;
  items: SearchResult[];
}

export interface SourceHealthItem {
  id: string;
  name: string;
  provider_label: string;
  feed_url: string | null;
  group: string | null;
  enabled: boolean | null;
  last_fetched_at: string | null;
  recent_article_count: number;
  error_status: string | null;
  error_message: string | null;
}

export interface SourceListResponse {
  provider: string;
  metadata_available: boolean;
  status: string;
  message: string;
  total: number;
  items: SourceHealthItem[];
}

export interface RuntimeSettings {
  api_workers: number;
  inspector_worker_processes: number;
  scheduler_enabled: boolean;
  scheduler_interval_seconds: number;
  ingestion_concurrency: number;
  summarization_concurrency: number;
  clustering_batch_size: number;
  clustering_concurrency: number;
  ingestion_active: boolean;
}

export interface HealthResponse {
  status: string;
  app: string;
  db: string;
  miniflux_configured: boolean;
  miniflux_reachable: boolean;
  miniflux_usable: boolean;
  runtime: RuntimeSettings;
  timestamp: string;
}

export interface ClusterDebugThresholds {
  score_threshold: number;
  title_signal_threshold: number;
  entity_overlap_threshold: number;
  keyword_overlap_threshold: number;
  topic_semantic_score_threshold: number;
  attach_override_title_similarity_threshold: number;
  attach_override_time_proximity_threshold: number;
  min_sources_for_api: number;
}

export interface ClusterDebugScoreBreakdown {
  average_similarity_score: number;
  average_title_similarity: number;
  average_entity_jaccard: number;
  average_keyword_jaccard: number;
  average_semantic_score: number;
  average_time_proximity: number;
  score_formula: string;
  semantic_formula: string;
}

export interface ClusterDebugJoinDecision {
  article_id: number;
  article_title: string;
  publisher: string;
  decision: string;
  reason: string;
  selected_cluster_id: string | null;
  selected_score: number;
  title_similarity: number;
  entity_jaccard: number;
  keyword_jaccard: number;
  semantic_score: number;
  entity_overlap: number;
  keyword_overlap: number;
  topic_match: boolean;
  time_proximity: number;
  signal_gate_passed: boolean;
  signal_reasons: string[];
  warnings: string[];
}

export interface ClusterDebugExplanation {
  grouping_reason: string;
  thresholds: ClusterDebugThresholds;
  threshold_results: Record<string, boolean>;
  top_shared_entities: string[];
  top_shared_keywords: string[];
  score_breakdown: ClusterDebugScoreBreakdown;
  decision_counts: Record<string, number>;
  recent_join_decisions: ClusterDebugJoinDecision[];
  warnings: string[];
}

export interface ClusterDebugItem {
  cluster_id: string;
  status: string;
  score: number;
  topic: string;
  source_count: number;
  visibility_threshold: number;
  promotion_eligible: boolean;
  promoted_at: string | null;
  previous_status: string | null;
  promotion_reason: string | null;
  promotion_explanation: string | null;
  promotion_blockers: string[];
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
