import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "../App";
import { USER_PREFERENCES_STORAGE_KEY } from "../utils/userPreferences";

function renderSettings() {
  return render(
    <MemoryRouter initialEntries={["/settings"]}>
      <AppRoutes />
    </MemoryRouter>
  );
}

function storedPreferences() {
  const raw = window.localStorage.getItem(USER_PREFERENCES_STORAGE_KEY);
  if (!raw) {
    throw new Error("Expected user preferences in localStorage");
  }

  return JSON.parse(raw) as Record<string, unknown>;
}

describe("SettingsPage", () => {
  it("persists preference changes and restores them after remount", () => {
    const { container, unmount } = renderSettings();

    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Compact mode" }));
    fireEvent.change(screen.getByLabelText("Default view"), { target: { value: "sources" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Show summaries" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "World" }));

    expect(container.querySelector(".app-shell")).toHaveClass("app-shell--dark");
    expect(container.querySelector(".app-shell")).toHaveClass("app-shell--compact");
    expect(storedPreferences()).toMatchObject({
      theme: "dark",
      compactMode: true,
      defaultView: "sources",
      showSummaries: false
    });
    expect(storedPreferences().topics).not.toContain("world");

    unmount();
    renderSettings();

    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("checkbox", { name: "Compact mode" })).toBeChecked();
    expect(screen.getByLabelText("Default view")).toHaveValue("sources");
    expect(screen.getByRole("checkbox", { name: "Show summaries" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "World" })).not.toBeChecked();
  });

  it("renders clean disabled placeholders for unfinished settings tabs", () => {
    renderSettings();

    expect(screen.getByRole("checkbox", { name: "Autoplay videos" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "+" })).toBeDisabled();

    fireEvent.click(screen.getByRole("tab", { name: "Account" }));
    expect(screen.getByText(/accounts are intentionally not part/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Privacy" }));
    expect(screen.getByText(/server-side preference storage/i)).toBeInTheDocument();
  });
});
