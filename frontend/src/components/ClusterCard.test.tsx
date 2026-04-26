import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SavedStoriesProvider } from "../context/SavedStoriesContext";
import { UserPreferencesProvider } from "../context/UserPreferencesContext";
import { ClusterCard } from "./ClusterCard";
import { USER_PREFERENCES_STORAGE_KEY } from "../utils/userPreferences";

describe("ClusterCard", () => {
  it("omits weak optional fields", () => {
    const { container, getByText } = render(
      <SavedStoriesProvider>
        <ClusterCard
          cluster={{
          cluster_id: "cluster-1",
          headline: "Transit Plan Advances",
          topic: "Transit Plan",
          summary: "   ",
          what_changed: "",
          why_it_matters: "",
          key_facts: [],
          timeline: [],
          timeline_events: [],
          sources: [],
          source_count: 0,
          primary_image_url: null,
          thumbnail_urls: [],
          region: null,
          story_type: "general",
          first_seen: "2026-04-23T00:00:00Z",
          last_updated: "2026-04-23T00:00:00Z",
          is_developing: false,
          is_breaking: false,
          confidence_score: Number.NaN,
          related_cluster_ids: [],
          score: Number.NaN,
          status: "active"
          }}
        />
      </SavedStoriesProvider>
    );

    getByText("Transit Plan Advances");
    expect(container.querySelector(".story-card__summary")).toBeNull();
    expect(container.querySelector(".story-card__score")).toBeNull();
    expect(getByText(/0 sources/i)).toBeInTheDocument();
  });

  it("renders and hides a cluster image when the image fails", () => {
    const { container } = render(
      <SavedStoriesProvider>
        <ClusterCard
          cluster={{
          cluster_id: "cluster-1",
          headline: "Transit Plan Advances",
          topic: "Transit Plan",
          summary: "Transit summary",
          what_changed: "",
          why_it_matters: "",
          key_facts: [],
          primary_image_url: "https://cdn.example.com/story.jpg",
          thumbnail_urls: ["https://cdn.example.com/story.jpg"],
          timeline: [],
          timeline_events: [],
          sources: [],
          source_count: 0,
          region: null,
          story_type: "general",
          first_seen: "2026-04-23T00:00:00Z",
          last_updated: "2026-04-23T00:00:00Z",
          is_developing: false,
          is_breaking: false,
          confidence_score: 0.8,
          related_cluster_ids: [],
          score: 0.8,
          status: "active"
          }}
        />
      </SavedStoriesProvider>
    );

    const image = container.querySelector(".story-card__image");
    expect(image).toHaveAttribute("src", "https://cdn.example.com/story.jpg");
    fireEvent.error(image as Element);
    expect(container.querySelector(".story-card__image")).toBeNull();
  });

  it("hides non-lead summaries when show summaries is disabled", () => {
    window.localStorage.setItem(
      USER_PREFERENCES_STORAGE_KEY,
      JSON.stringify({
        theme: "light",
        compactMode: false,
        autoplayVideos: false,
        defaultView: "timeline",
        language: "en",
        showSummaries: false,
        topics: ["world"]
      })
    );

    const { container } = render(
      <UserPreferencesProvider>
        <SavedStoriesProvider>
          <ClusterCard
            cluster={{
              cluster_id: "cluster-1",
              headline: "Transit Plan Advances",
              topic: "Transit Plan",
              summary: "Transit summary",
              what_changed: "",
              why_it_matters: "",
              key_facts: [],
              timeline: [],
              timeline_events: [],
              sources: [],
              source_count: 0,
              primary_image_url: null,
              thumbnail_urls: [],
              region: null,
              story_type: "general",
              first_seen: "2026-04-23T00:00:00Z",
              last_updated: "2026-04-23T00:00:00Z",
              is_developing: false,
              is_breaking: false,
              confidence_score: 0.8,
              related_cluster_ids: [],
              score: 0.8,
              status: "active"
            }}
          />
        </SavedStoriesProvider>
      </UserPreferencesProvider>
    );

    expect(container.querySelector(".story-card__summary")).toBeNull();
  });
});
