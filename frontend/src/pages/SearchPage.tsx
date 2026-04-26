import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchSearchResults } from "../api/client";
import { ImageWithFallback } from "../components/ImageWithFallback";
import type { SearchResponse, SearchResult, SearchResultType } from "../types";
import { formatReadableTimestamp, formatRelativeTime } from "../utils/format";

const SEARCH_LIMIT = 50;
const SEARCH_DEBOUNCE_MS = 300;

type SearchTab = "all" | "cluster" | "update" | "source";

const tabs: Array<{ id: SearchTab; label: string; countKey: "all" | "clusters" | "updates" | "sources" }> = [
  { id: "all", label: "All", countKey: "all" },
  { id: "cluster", label: "Clusters", countKey: "clusters" },
  { id: "update", label: "Updates", countKey: "updates" },
  { id: "source", label: "Sources", countKey: "sources" }
];

function tabMatchesResult(tab: SearchTab, result: SearchResult): boolean {
  return tab === "all" || result.type === tab;
}

function resultTypeLabel(type: SearchResultType): string {
  if (type === "cluster") {
    return "Cluster";
  }
  if (type === "update") {
    return "Update";
  }
  return "Source";
}

function matchedFieldLabel(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  return value.replace(/_/g, " ");
}

function SearchSkeletonList() {
  return (
    <div className="search-results-list search-results-list--skeleton" aria-hidden="true">
      {Array.from({ length: 4 }).map((_, index) => (
        <article className="search-result-card search-result-card--skeleton" key={index}>
          <div className="search-result-card__image" />
          <div className="search-result-card__copy">
            <span className="story-skeleton story-skeleton--line story-skeleton--tiny" />
            <span className="story-skeleton story-skeleton--headline" />
            <span className="story-skeleton story-skeleton--line" />
            <span className="story-skeleton story-skeleton--line story-skeleton--short" />
          </div>
        </article>
      ))}
    </div>
  );
}

function SearchResultCard({ result }: { result: SearchResult }) {
  const readable = formatReadableTimestamp(result.last_updated);
  const relative = formatRelativeTime(result.last_updated);
  const updatedLabel = readable && !relative.startsWith("(") ? `${relative} | ${readable}` : readable;
  const matchedField = matchedFieldLabel(result.matched_field);
  const topic = result.topic?.trim();

  return (
    <article className="search-result-card" data-result-type={result.type}>
      <ImageWithFallback src={result.thumbnail_url} label={topic} className="search-result-card__image" />

      <div className="search-result-card__copy">
        <div className="search-result-card__meta">
          <span className="search-result-card__type">{resultTypeLabel(result.type)}</span>
          {topic && <span>{topic}</span>}
          <span>
            {result.source_count} source{result.source_count === 1 ? "" : "s"}
          </span>
          <span>
            {result.update_count} update{result.update_count === 1 ? "" : "s"}
          </span>
          {result.source_name && <span>{result.source_name}</span>}
        </div>

        <Link to={`/story/${result.cluster_id}`} className="search-result-card__title">
          {result.title}
        </Link>
        <p>{result.snippet}</p>

        <div className="search-result-card__footer">
          {updatedLabel && <span>Updated {updatedLabel}</span>}
          {matchedField && <span>Matched {matchedField}</span>}
          {result.article_url && (
            <a href={result.article_url} target="_blank" rel="noreferrer">
              Source article
            </a>
          )}
        </div>
      </div>
    </article>
  );
}

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") ?? "";
  const [draftQuery, setDraftQuery] = useState(initialQuery);
  const [query, setQuery] = useState(initialQuery.trim());
  const [activeTab, setActiveTab] = useState<SearchTab>("all");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      const nextQuery = draftQuery.trim();
      setQuery(nextQuery);
      setSearchParams(nextQuery ? { q: nextQuery } : {}, { replace: true });
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(handle);
  }, [draftQuery, setSearchParams]);

  useEffect(() => {
    if (!query) {
      setResponse(null);
      setError(null);
      setLoading(false);
      setActiveTab("all");
      return;
    }

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setError(null);

    fetchSearchResults({ q: query, limit: SEARCH_LIMIT })
      .then((result) => {
        if (requestIdRef.current !== requestId) {
          return;
        }
        setResponse(result);
        setActiveTab((current) => {
          if (current === "all") {
            return current;
          }
          const tab = tabs.find((item) => item.id === current);
          return tab && result.counts[tab.countKey] > 0 ? current : "all";
        });
      })
      .catch((err) => {
        if (requestIdRef.current !== requestId) {
          return;
        }
        setError((err as Error).message);
        setResponse(null);
      })
      .finally(() => {
        if (requestIdRef.current === requestId) {
          setLoading(false);
        }
      });
  }, [query, retryCount]);

  const visibleResults = useMemo(() => {
    const items = response?.items ?? [];
    return items.filter((item) => tabMatchesResult(activeTab, item));
  }, [activeTab, response]);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuery = draftQuery.trim();
    setQuery(nextQuery);
    setSearchParams(nextQuery ? { q: nextQuery } : {}, { replace: true });
  }

  function retrySearch() {
    const nextQuery = draftQuery.trim() || query;
    setQuery(nextQuery);
    setSearchParams(nextQuery ? { q: nextQuery } : {}, { replace: true });
    setRetryCount((count) => count + 1);
  }

  const hasQuery = query.length > 0;
  const hasResults = visibleResults.length > 0;

  return (
    <div className="public-page search-page">
      <header className="search-page__header">
        <div>
          <p className="eyebrow">Search</p>
          <h1>Find stories, updates, and sources</h1>
        </div>

        <form className="search-box" role="search" onSubmit={submitSearch}>
          <label className="sr-only" htmlFor="roundup-search-input">
            Search Roundup
          </label>
          <input
            id="roundup-search-input"
            type="search"
            placeholder="Search headlines, updates, sources, topics"
            value={draftQuery}
            onChange={(event) => setDraftQuery(event.target.value)}
          />
          <button type="submit">Search</button>
        </form>
      </header>

      {hasQuery && response && (
        <div className="search-tabs" role="tablist" aria-label="Search result filters">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`search-tabs__button${activeTab === tab.id ? " search-tabs__button--active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span>{tab.label}</span>
              <span>{response.counts[tab.countKey]}</span>
            </button>
          ))}
        </div>
      )}

      <main className="search-page__body" aria-live="polite">
        {!hasQuery && (
          <section className="state-panel">
            <p className="eyebrow">Ready when you are</p>
            <h2>Search live Roundup data</h2>
            <p>Look up current clusters, recent updates, publishers, article titles, and topics from the backend.</p>
          </section>
        )}

        {loading && <SearchSkeletonList />}

        {!loading && hasQuery && error && (
          <section className="state-panel state-panel--error" role="alert">
            <p className="eyebrow">Search error</p>
            <h2>Could not load search results</h2>
            <p>{error}</p>
            <button type="button" className="secondary-action" onClick={retrySearch}>
              Retry search
            </button>
          </section>
        )}

        {!loading && hasQuery && !error && response && response.total === 0 && (
          <section className="state-panel">
            <p className="eyebrow">No matches</p>
            <h2>No results for "{response.query}"</h2>
            <p>Try a headline, publisher, source, update detail, or topic from the live feed.</p>
          </section>
        )}

        {!loading && hasQuery && !error && response && response.total > 0 && !hasResults && (
          <section className="state-panel">
            <p className="eyebrow">No matches in this tab</p>
            <h2>No {tabs.find((tab) => tab.id === activeTab)?.label.toLowerCase()} results for "{response.query}"</h2>
            <p>Switch tabs to see the other matching result types.</p>
          </section>
        )}

        {!loading && hasResults && (
          <section className="search-results-panel" aria-labelledby="search-results-heading">
            <div className="dashboard-section__header">
              <h2 id="search-results-heading">Results for "{response?.query}"</h2>
              <p>
                Showing {visibleResults.length} of {response?.total ?? 0} typed results from live Roundup data.
              </p>
            </div>
            <div className="search-results-list">
              {visibleResults.map((result) => (
                <SearchResultCard key={result.id} result={result} />
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
