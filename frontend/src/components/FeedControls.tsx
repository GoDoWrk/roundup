type SortMode = "top" | "latest";

interface FeedControlsProps {
  sortMode: SortMode;
  publishers: string[];
  publisherFilter: string;
  onSortModeChange: (mode: SortMode) => void;
  onPublisherFilterChange: (publisher: string) => void;
}

export function FeedControls({
  sortMode,
  publishers,
  publisherFilter,
  onSortModeChange,
  onPublisherFilterChange
}: FeedControlsProps) {
  return (
    <section className="feed-controls" aria-label="Feed controls">
      <div className="feed-controls__group" role="toolbar" aria-label="Sort stories">
        <button
          type="button"
          className={sortMode === "top" ? "feed-controls__button feed-controls__button--active" : "feed-controls__button"}
          aria-pressed={sortMode === "top"}
          onClick={() => onSortModeChange("top")}
        >
          Top / Most Important
        </button>
        <button
          type="button"
          className={
            sortMode === "latest" ? "feed-controls__button feed-controls__button--active" : "feed-controls__button"
          }
          aria-pressed={sortMode === "latest"}
          onClick={() => onSortModeChange("latest")}
        >
          Latest Updates
        </button>
      </div>

      {publishers.length > 1 && (
        <label className="feed-controls__filter">
          <span>Source</span>
          <select value={publisherFilter} onChange={(event) => onPublisherFilterChange(event.target.value)}>
            <option value="all">All sources</option>
            {publishers.map((publisher) => (
              <option key={publisher} value={publisher}>
                {publisher}
              </option>
            ))}
          </select>
        </label>
      )}
    </section>
  );
}
