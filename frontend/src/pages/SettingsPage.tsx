import { useCallback, useEffect, useState } from "react";
import { fetchSources } from "../api/client";
import { useSavedStories } from "../context/SavedStoriesContext";
import { useUserPreferences } from "../context/UserPreferencesContext";
import type { SourceHealthItem, SourceListResponse } from "../types";
import { formatReadableTimestamp } from "../utils/format";
import {
  DEFAULT_USER_PREFERENCES,
  type ThemePreference
} from "../utils/userPreferences";

type SettingsTab = "preferences" | "sources";

const settingsTabs: Array<{ id: SettingsTab; label: string }> = [
  { id: "preferences", label: "Preferences" },
  { id: "sources", label: "Sources" }
];

const themeOptions: Array<{ value: ThemePreference; label: string }> = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" }
];

function ToggleSwitch({
  checked,
  disabled = false,
  label,
  onChange
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className={`settings-switch${disabled ? " settings-switch--disabled" : ""}`}>
      <span>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        aria-label={label}
      />
      <span className="settings-switch__track" aria-hidden="true" />
    </label>
  );
}

function sourceStatus(source: SourceHealthItem): { label: string; modifier: string } {
  if (source.error_status === "error") {
    return { label: "Error", modifier: "error" };
  }
  if (source.enabled === true) {
    return { label: "Enabled", modifier: "enabled" };
  }
  if (source.enabled === false) {
    return { label: "Disabled", modifier: "disabled" };
  }
  return { label: "Unknown", modifier: "unknown" };
}

function articleCountLabel(count: number): string {
  return `${count} recent ${count === 1 ? "article" : "articles"}`;
}

function SourcesTab({
  data,
  error,
  loading,
  onRefresh
}: {
  data: SourceListResponse | null;
  error: string | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  return (
    <section className="settings-card settings-sources" aria-labelledby="settings-sources-heading">
      <div className="settings-sources__header">
        <div>
          <h2 id="settings-sources-heading">Sources</h2>
          <p>Read-only ingestion source status from the live Roundup backend.</p>
        </div>
        <button type="button" className="secondary-button settings-sources__refresh" onClick={onRefresh} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="settings-source-state settings-source-state--error" role="alert">
          <h3>Source health is unavailable</h3>
          <p>{error}</p>
        </div>
      )}

      {!error && loading && (
        <div className="settings-source-state" aria-live="polite">
          <h3>Loading sources</h3>
          <p>Checking configured ingestion sources and recent article activity.</p>
        </div>
      )}

      {!error && !loading && data && (
        <>
          <div className="settings-sources__summary">
            <span className={`source-status source-status--${data.metadata_available ? "enabled" : "unknown"}`}>
              {data.metadata_available ? "Metadata available" : "Metadata unavailable"}
            </span>
            <span>{data.total} {data.metadata_available ? "configured" : "observed"} {data.total === 1 ? "source" : "sources"}</span>
            <span>{data.provider}</span>
          </div>

          {!data.metadata_available && data.items.length > 0 && <p className="settings-sources__message">{data.message}</p>}

          {data.items.length === 0 ? (
            <div className="settings-source-state">
              <h3>No source metadata yet</h3>
              <p>{data.message || "Run ingestion once to populate recent source activity."}</p>
            </div>
          ) : (
            <div className="settings-source-table" role="table" aria-label="Configured ingestion sources">
              <div className="settings-source-table__row settings-source-table__row--head" role="row">
                <span role="columnheader">Source</span>
                <span role="columnheader">Location</span>
                <span role="columnheader">Status</span>
                <span role="columnheader">Last fetched</span>
                <span role="columnheader">Recent articles</span>
              </div>

              {data.items.map((source) => {
                const status = sourceStatus(source);
                const lastFetched = formatReadableTimestamp(source.last_fetched_at) ?? "Not available";
                const location = source.feed_url || source.provider_label;

                return (
                  <div key={source.id} className="settings-source-table__row" role="row">
                    <span role="cell" className="settings-source-table__source">
                      <strong>{source.name}</strong>
                      {source.group && <small>{source.group}</small>}
                    </span>
                    <span role="cell" className="settings-source-table__url" title={location}>
                      {location}
                    </span>
                    <span role="cell">
                      <span className={`source-status source-status--${status.modifier}`}>{status.label}</span>
                      {source.error_message && <small className="settings-source-table__error">{source.error_message}</small>}
                    </span>
                    <span role="cell">{lastFetched}</span>
                    <span role="cell">{articleCountLabel(source.recent_article_count)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </section>
  );
}

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("preferences");
  const [sources, setSources] = useState<SourceListResponse | null>(null);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [sourcesLoaded, setSourcesLoaded] = useState(false);
  const { preferences, updatePreferences } = useUserPreferences();
  const { savedStories, savedCount, unsaveStory } = useSavedStories();

  const loadSources = useCallback(async () => {
    setSourcesLoading(true);
    setSourcesError(null);

    try {
      const response = await fetchSources();
      setSources(response);
      setSourcesLoaded(true);
    } catch (err) {
      setSourcesError((err as Error).message);
    } finally {
      setSourcesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === "sources" && !sourcesLoaded && !sourcesLoading) {
      void loadSources();
    }
  }, [activeTab, loadSources, sourcesLoaded, sourcesLoading]);

  function clearSavedStories() {
    for (const record of savedStories) {
      unsaveStory(record.cluster_id);
    }
  }

  function resetPreferences() {
    updatePreferences(DEFAULT_USER_PREFERENCES);
  }

  return (
    <div className="public-page settings-page">
      <header className="settings-header">
        <div>
          <p className="eyebrow">Local settings</p>
          <h1>Settings</h1>
        </div>
        <p>Preferences are stored in this browser and do not require an account.</p>
      </header>

      <div className="settings-tabs" role="tablist" aria-label="Settings sections">
        {settingsTabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`settings-tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`settings-panel-${tab.id}`}
            className={`settings-tabs__button${activeTab === tab.id ? " settings-tabs__button--active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <main
        id={`settings-panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`settings-tab-${activeTab}`}
        className="settings-panel"
      >
        {activeTab === "preferences" && (
          <div className="settings-preferences-grid">
            <section className="settings-card" aria-labelledby="settings-display-heading">
              <h2 id="settings-display-heading">Display</h2>
              <p>These preferences change the local interface immediately in this browser.</p>

              <div className="settings-field">
                <span className="settings-field__label">Theme</span>
                <div className="settings-segmented" role="group" aria-label="Theme">
                  {themeOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`settings-segmented__button${
                        preferences.theme === option.value ? " settings-segmented__button--active" : ""
                      }`}
                      aria-pressed={preferences.theme === option.value}
                      onClick={() => updatePreferences({ theme: option.value })}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <ToggleSwitch
                label="Compact mode"
                checked={preferences.compactMode}
                onChange={(checked) => updatePreferences({ compactMode: checked })}
              />

              <ToggleSwitch
                label="Show summaries"
                checked={preferences.showSummaries}
                onChange={(checked) => updatePreferences({ showSummaries: checked })}
              />
            </section>

            <section className="settings-card" aria-labelledby="settings-local-data-heading">
              <h2 id="settings-local-data-heading">Local Data</h2>
              <p>Clear data stored only in this browser.</p>

              <div className="settings-actions">
                <button type="button" className="secondary-button" onClick={clearSavedStories} disabled={savedCount === 0}>
                  Clear saved stories
                </button>
                <button type="button" className="secondary-button" onClick={resetPreferences}>
                  Reset preferences
                </button>
              </div>

              <p className="muted">
                {savedCount} saved {savedCount === 1 ? "story" : "stories"} in this browser.
              </p>
            </section>
          </div>
        )}

        {activeTab === "sources" && (
          <SourcesTab data={sources} error={sourcesError} loading={sourcesLoading} onRefresh={() => void loadSources()} />
        )}
      </main>
    </div>
  );
}
