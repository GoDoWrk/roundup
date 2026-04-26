import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { SAVED_STORIES_STORAGE_KEY } from "../utils/savedStories";
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

function mockSourcesResponse(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(typeof body === "string" ? body : JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" }
      })
    )
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SettingsPage", () => {
  it("persists preference changes and restores them after remount", () => {
    const { container, unmount } = renderSettings();

    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Compact mode" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Show summaries" }));

    expect(container.querySelector(".app-shell")).toHaveClass("app-shell--dark");
    expect(container.querySelector(".app-shell")).toHaveClass("app-shell--compact");
    expect(storedPreferences()).toMatchObject({
      theme: "dark",
      compactMode: true,
      showSummaries: false
    });

    unmount();
    renderSettings();

    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("checkbox", { name: "Compact mode" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Show summaries" })).not.toBeChecked();
  });

  it("hides unfinished settings controls and tabs", () => {
    renderSettings();

    expect(screen.queryByRole("checkbox", { name: "Autoplay videos" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Default view")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Language")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Topics" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Alerts" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Account" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Privacy" })).not.toBeInTheDocument();
  });

  it("clears browser-local saved stories and resets preferences", () => {
    window.localStorage.setItem(
      SAVED_STORIES_STORAGE_KEY,
      JSON.stringify([
        {
          cluster_id: "cluster-1",
          saved_at: "2026-04-23T00:00:00Z",
          story: {
            cluster_id: "cluster-1",
            headline: "Saved Story",
            summary: "Summary",
            what_changed: "",
            why_it_matters: "",
            key_facts: [],
            timeline: [],
            timeline_events: [],
            sources: [],
            source_count: 0,
            primary_image_url: null,
            thumbnail_urls: [],
            topic: "World",
            region: null,
            story_type: "general",
            first_seen: "2026-04-23T00:00:00Z",
            last_updated: "2026-04-23T00:00:00Z",
            is_developing: false,
            is_breaking: false,
            confidence_score: 0.5,
            related_cluster_ids: [],
            score: 0.5,
            status: "active"
          }
        }
      ])
    );

    renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear saved stories" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset preferences" }));

    expect(window.localStorage.getItem(SAVED_STORIES_STORAGE_KEY)).toBe("[]");
    expect(storedPreferences()).toMatchObject({ theme: "light", compactMode: false, showSummaries: true });
  });

  it("loads and renders configured source health data in the Sources tab", async () => {
    mockSourcesResponse({
      provider: "miniflux",
      metadata_available: true,
      status: "ok",
      message: "Configured Miniflux feeds with recent Roundup ingestion activity.",
      total: 1,
      items: [
        {
          id: "miniflux:42",
          name: "Reuters",
          provider_label: "Miniflux feed",
          feed_url: "https://reuters.example.com/feed.xml",
          group: "World News",
          enabled: true,
          last_fetched_at: "2026-04-25T12:00:00Z",
          recent_article_count: 3,
          error_status: "ok",
          error_message: null
        }
      ]
    });

    renderSettings();
    fireEvent.click(screen.getByRole("tab", { name: "Sources" }));

    expect(await screen.findByRole("heading", { name: "Sources" })).toBeInTheDocument();
    expect(await screen.findByText("Reuters")).toBeInTheDocument();
    expect(screen.getByText("World News")).toBeInTheDocument();
    expect(screen.getByText("https://reuters.example.com/feed.xml")).toBeInTheDocument();
    expect(screen.getByText("Enabled")).toBeInTheDocument();
    expect(screen.getByText("3 recent articles")).toBeInTheDocument();
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/sources", expect.any(Object));
  });

  it("shows a graceful unavailable empty state for missing source metadata", async () => {
    mockSourcesResponse({
      provider: "roundup",
      metadata_available: false,
      status: "empty",
      message: "Miniflux source metadata is not configured; showing recent article publishers when available.",
      total: 0,
      items: []
    });

    renderSettings();
    fireEvent.click(screen.getByRole("tab", { name: "Sources" }));

    expect(await screen.findByText("Metadata unavailable")).toBeInTheDocument();
    expect(screen.getByText("No source metadata yet")).toBeInTheDocument();
    expect(screen.getByText(/Miniflux source metadata is not configured/i)).toBeInTheDocument();
  });

  it("shows a non-crashing error state when source health request fails", async () => {
    mockSourcesResponse("backend unavailable", 503);

    renderSettings();
    fireEvent.click(screen.getByRole("tab", { name: "Sources" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Source health is unavailable");
    expect(screen.getByText(/\/api\/sources returned 503/i)).toBeInTheDocument();
  });
});
