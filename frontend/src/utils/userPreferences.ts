export const USER_PREFERENCES_STORAGE_KEY = "roundup-user-preferences-v1";
const LEGACY_DARK_MODE_STORAGE_KEY = "roundup-dark-mode";

export type ThemePreference = "light" | "dark" | "system";
export type DefaultViewPreference = "timeline" | "summary" | "sources";

export interface TopicPreference {
  id: string;
  label: string;
}

export interface UserPreferences {
  theme: ThemePreference;
  compactMode: boolean;
  autoplayVideos: boolean;
  defaultView: DefaultViewPreference;
  language: "en";
  showSummaries: boolean;
  topics: string[];
}

export const TOPIC_PREFERENCES: TopicPreference[] = [
  { id: "world", label: "World" },
  { id: "us", label: "U.S." },
  { id: "politics", label: "Politics" },
  { id: "business", label: "Business" },
  { id: "technology", label: "Technology" },
  { id: "science", label: "Science" },
  { id: "health", label: "Health" },
  { id: "entertainment", label: "Entertainment" }
];

const THEME_VALUES: ThemePreference[] = ["light", "dark", "system"];
const DEFAULT_VIEW_VALUES: DefaultViewPreference[] = ["timeline", "summary", "sources"];
const TOPIC_IDS = new Set(TOPIC_PREFERENCES.map((topic) => topic.id));

export const DEFAULT_USER_PREFERENCES: UserPreferences = {
  theme: "dark",
  compactMode: false,
  autoplayVideos: false,
  defaultView: "timeline",
  language: "en",
  showSummaries: true,
  topics: TOPIC_PREFERENCES.map((topic) => topic.id)
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeTopics(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return DEFAULT_USER_PREFERENCES.topics;
  }

  const uniqueTopics = new Set<string>();
  for (const item of value) {
    if (typeof item === "string" && TOPIC_IDS.has(item)) {
      uniqueTopics.add(item);
    }
  }

  return [...uniqueTopics];
}

export function normalizeUserPreferences(value: unknown): UserPreferences {
  if (!isRecord(value)) {
    return DEFAULT_USER_PREFERENCES;
  }

  const theme = typeof value.theme === "string" && THEME_VALUES.includes(value.theme as ThemePreference)
    ? (value.theme as ThemePreference)
    : DEFAULT_USER_PREFERENCES.theme;
  const defaultView =
    typeof value.defaultView === "string" && DEFAULT_VIEW_VALUES.includes(value.defaultView as DefaultViewPreference)
      ? (value.defaultView as DefaultViewPreference)
      : DEFAULT_USER_PREFERENCES.defaultView;

  return {
    theme,
    compactMode: typeof value.compactMode === "boolean" ? value.compactMode : DEFAULT_USER_PREFERENCES.compactMode,
    autoplayVideos:
      typeof value.autoplayVideos === "boolean" ? value.autoplayVideos : DEFAULT_USER_PREFERENCES.autoplayVideos,
    defaultView,
    language: "en",
    showSummaries: typeof value.showSummaries === "boolean" ? value.showSummaries : DEFAULT_USER_PREFERENCES.showSummaries,
    topics: normalizeTopics(value.topics)
  };
}

export function readUserPreferences(): UserPreferences {
  try {
    const raw = window.localStorage.getItem(USER_PREFERENCES_STORAGE_KEY);
    if (raw) {
      return normalizeUserPreferences(JSON.parse(raw));
    }

    if (window.localStorage.getItem(LEGACY_DARK_MODE_STORAGE_KEY) === "true") {
      return { ...DEFAULT_USER_PREFERENCES, theme: "dark" };
    }

    return DEFAULT_USER_PREFERENCES;
  } catch {
    return DEFAULT_USER_PREFERENCES;
  }
}

export function writeUserPreferences(preferences: UserPreferences): void {
  try {
    window.localStorage.setItem(USER_PREFERENCES_STORAGE_KEY, JSON.stringify(normalizeUserPreferences(preferences)));
  } catch {
    // Local storage can be unavailable in locked-down browsers.
  }
}
