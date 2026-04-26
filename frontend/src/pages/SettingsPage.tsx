import { useState } from "react";
import { useUserPreferences } from "../context/UserPreferencesContext";
import {
  TOPIC_PREFERENCES,
  type DefaultViewPreference,
  type ThemePreference
} from "../utils/userPreferences";

type SettingsTab = "preferences" | "alerts" | "sources" | "account" | "privacy";

const settingsTabs: Array<{ id: SettingsTab; label: string }> = [
  { id: "preferences", label: "Preferences" },
  { id: "alerts", label: "Alerts" },
  { id: "sources", label: "Sources" },
  { id: "account", label: "Account" },
  { id: "privacy", label: "Privacy" }
];

const themeOptions: Array<{ value: ThemePreference; label: string }> = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" }
];

const defaultViewOptions: Array<{ value: DefaultViewPreference; label: string }> = [
  { value: "timeline", label: "Timeline" },
  { value: "summary", label: "Summary" },
  { value: "sources", label: "Sources" }
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

function PlaceholderTab({ title, children }: { title: string; children: string }) {
  return (
    <section className="settings-placeholder-panel" aria-labelledby={`settings-${title.toLowerCase()}-heading`}>
      <p className="eyebrow">Not configured</p>
      <h2 id={`settings-${title.toLowerCase()}-heading`}>{title}</h2>
      <p>{children}</p>
    </section>
  );
}

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("preferences");
  const { preferences, updatePreferences } = useUserPreferences();
  const selectedTopics = new Set(preferences.topics);

  function toggleTopic(topicId: string, checked: boolean) {
    updatePreferences((current) => {
      const nextTopics = new Set(current.topics);
      if (checked) {
        nextTopics.add(topicId);
      } else {
        nextTopics.delete(topicId);
      }

      return { ...current, topics: [...nextTopics] };
    });
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
                label="Autoplay videos"
                checked={preferences.autoplayVideos}
                disabled
                onChange={() => undefined}
              />

              <h3>Content</h3>

              <label className="settings-field">
                <span className="settings-field__label">Default view</span>
                <select
                  value={preferences.defaultView}
                  onChange={(event) => updatePreferences({ defaultView: event.target.value as DefaultViewPreference })}
                >
                  {defaultViewOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="settings-field">
                <span className="settings-field__label">Language</span>
                <select value={preferences.language} onChange={() => undefined}>
                  <option value="en">English</option>
                </select>
              </label>

              <ToggleSwitch
                label="Show summaries"
                checked={preferences.showSummaries}
                onChange={(checked) => updatePreferences({ showSummaries: checked })}
              />
            </section>

            <section className="settings-card" aria-labelledby="settings-topics-heading">
              <h2 id="settings-topics-heading">Topics</h2>
              <p>Choose topics you want to see more of.</p>

              <div className="settings-topic-list">
                {TOPIC_PREFERENCES.map((topic) => (
                  <label key={topic.id} className="settings-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedTopics.has(topic.id)}
                      onChange={(event) => toggleTopic(topic.id, event.target.checked)}
                    />
                    <span>{topic.label}</span>
                  </label>
                ))}
              </div>

              <div className="settings-custom-topic" aria-disabled="true">
                <button type="button" disabled>
                  +
                </button>
                <span>Add custom topic</span>
              </div>
            </section>
          </div>
        )}

        {activeTab === "alerts" && (
          <PlaceholderTab title="Alerts">
            Alert delivery is reserved for a later notification system and is disabled in this local-only settings pass.
          </PlaceholderTab>
        )}
        {activeTab === "sources" && (
          <PlaceholderTab title="Sources">
            Source controls will be added after source preference behavior is backed by a clear public product contract.
          </PlaceholderTab>
        )}
        {activeTab === "account" && (
          <PlaceholderTab title="Account">
            Accounts are intentionally not part of this PR, so there are no login, profile, or authentication settings.
          </PlaceholderTab>
        )}
        {activeTab === "privacy" && (
          <PlaceholderTab title="Privacy">
            Privacy controls will remain local until Roundup adds user accounts or server-side preference storage.
          </PlaceholderTab>
        )}
      </main>
    </div>
  );
}
