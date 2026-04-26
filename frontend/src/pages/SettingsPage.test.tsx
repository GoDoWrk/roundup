import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
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
