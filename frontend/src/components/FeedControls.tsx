type SortMode = "top" | "latest";

interface FeedControlsProps {
  sortMode: SortMode;
  topics: string[];
  topicFilter: string;
  onSortModeChange: (mode: SortMode) => void;
  onTopicFilterChange: (topic: string) => void;
}

export function FeedControls({
  sortMode,
  topics,
  topicFilter,
  onSortModeChange,
  onTopicFilterChange
}: FeedControlsProps) {
  return (
    <section className="feed-controls" aria-label="Feed controls">
      <label className="feed-controls__field">
        <span>Topic</span>
        <select
          value={topicFilter}
          aria-label="Topic"
          onChange={(event) => onTopicFilterChange(event.target.value)}
        >
          <option value="all">All topics</option>
          {topics.map((topic) => (
            <option key={topic} value={topic}>
              {topic}
            </option>
          ))}
        </select>
      </label>

      <label className="feed-controls__field">
        <span>Sort</span>
        <select
          value={sortMode}
          aria-label="Sort"
          onChange={(event) => onSortModeChange(event.target.value as SortMode)}
        >
          <option value="top">Top / Most Important</option>
          <option value="latest">Latest Updates</option>
        </select>
      </label>
    </section>
  );
}
