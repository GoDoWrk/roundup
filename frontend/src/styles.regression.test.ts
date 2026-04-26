import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

function rulesFor(selector: string) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return [...styles.matchAll(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`, "g"))].map((match) => match[1]);
}

describe("story card layout CSS", () => {
  it("does not double-grid linked supporting story cards", () => {
    expect(rulesFor(".story-card--linked.story-card--supporting")).toContainEqual(expect.stringContaining("display: block"));
  });

  it("avoids single-character headline wrapping in tight card columns", () => {
    const headlineRules = rulesFor(".story-card__headline").join("\n");
    expect(headlineRules).toContain("overflow-wrap: break-word");
    expect(headlineRules).toContain("word-break: normal");
  });
});
