import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "../App";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>
  );
}

describe("hidden alerts route", () => {
  it("redirects alerts to the saved stories surface", () => {
    renderAt("/alerts");

    expect(screen.getByRole("heading", { name: "Saved Stories" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Saved$/ })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: /^Alerts$/ })).not.toBeInTheDocument();
  });
});
