import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClusterCard } from "./ClusterCard";

describe("ClusterCard", () => {
  it("omits weak optional fields", () => {
    const { container, getByText } = render(
      <ClusterCard
        cluster={{
          cluster_id: "cluster-1",
          headline: "Transit Plan Advances",
          summary: "   ",
          what_changed: "",
          why_it_matters: "",
          timeline: [],
          sources: [],
          first_seen: "2026-04-23T00:00:00Z",
          last_updated: "2026-04-23T00:00:00Z",
          score: Number.NaN,
          status: "active"
        }}
      />
    );

    getByText("Transit Plan Advances");
    expect(container.querySelector(".story-card__summary")).toBeNull();
    expect(container.querySelector(".story-card__score")).toBeNull();
    expect(getByText(/0 sources/i)).toBeInTheDocument();
  });
});
