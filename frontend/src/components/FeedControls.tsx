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
      <label className="feed-controls__filter">
        <span>Topic</span>
        <select value={topicFilter} onChange={(event) => onTopicFilterChange(event.target.value)}>
          <option value="all">All topics</option>
          {topics.map((topic) => (
            <option key={topic} value={topic}>
              {topic}
            </option>
          ))}
        </select>
      </label>

      <div className="feed-controls__group" role="toolbar" aria-label="Sort stories">
        <button
          type="button"
          className={sortMode === "top" ? "feed-controls__button feed-controls__button--active" : "feed-controls__button"}
          aria-pressed={sortMode === "top"}
          onClick={() => onSortModeChange("top")}
        >
          Sort: Relevance
        </button>
        <button
          type="button"
          className={
            sortMode === "latest" ? "feed-controls__button feed-controls__button--active" : "feed-controls__button"
          }
          aria-pressed={sortMode === "latest"}
          onClick={() => onSortModeChange("latest")}
        >
          Sort: Latest
        </button>
      </div>
    </section>
  );
}
