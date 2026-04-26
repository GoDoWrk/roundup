import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  DEFAULT_USER_PREFERENCES,
  USER_PREFERENCES_STORAGE_KEY,
  normalizeUserPreferences,
  readUserPreferences,
  writeUserPreferences,
  type UserPreferences
} from "../utils/userPreferences";

interface UserPreferencesContextValue {
  preferences: UserPreferences;
  resolvedTheme: "light" | "dark";
  updatePreferences: (updater: Partial<UserPreferences> | ((current: UserPreferences) => UserPreferences)) => void;
}

const UserPreferencesContext = createContext<UserPreferencesContextValue | null>(null);

function getSystemTheme(): "light" | "dark" {
  try {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function UserPreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState<UserPreferences>(() => readUserPreferences());
  const [systemTheme, setSystemTheme] = useState<"light" | "dark">(() => getSystemTheme());

  useEffect(() => {
    function handleStorage(event: StorageEvent) {
      if (event.key === USER_PREFERENCES_STORAGE_KEY) {
        setPreferences(readUserPreferences());
      }
    }

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  useEffect(() => {
    let media: MediaQueryList | null = null;
    try {
      media = window.matchMedia?.("(prefers-color-scheme: dark)") ?? null;
    } catch {
      media = null;
    }

    if (!media) {
      return undefined;
    }

    const handleChange = () => setSystemTheme(media?.matches ? "dark" : "light");
    handleChange();
    media.addEventListener?.("change", handleChange);
    return () => media?.removeEventListener?.("change", handleChange);
  }, []);

  const updatePreferences = useCallback<UserPreferencesContextValue["updatePreferences"]>((updater) => {
    setPreferences((current) => {
      const next = normalizeUserPreferences(typeof updater === "function" ? updater(current) : { ...current, ...updater });
      writeUserPreferences(next);
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({
      preferences,
      resolvedTheme: preferences.theme === "system" ? systemTheme : preferences.theme,
      updatePreferences
    }),
    [preferences, systemTheme, updatePreferences]
  );

  return <UserPreferencesContext.Provider value={value}>{children}</UserPreferencesContext.Provider>;
}

export function useUserPreferences() {
  const context = useContext(UserPreferencesContext);
  if (!context) {
    return {
      preferences: DEFAULT_USER_PREFERENCES,
      resolvedTheme: DEFAULT_USER_PREFERENCES.theme === "dark" ? "dark" : "light",
      updatePreferences: () => undefined
    } satisfies UserPreferencesContextValue;
  }

  return context;
}
