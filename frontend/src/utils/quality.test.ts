import { describe, expect, it } from "vitest";
import { evaluateTextQuality } from "./quality";

describe("evaluateTextQuality", () => {
  it("flags blank text", () => {
    const flags = evaluateTextQuality("   ");
    expect(flags.isBlank).toBe(true);
  });

  it("flags very short text", () => {
    const flags = evaluateTextQuality("short phrase only");
    expect(flags.isVeryShort).toBe(true);
  });

  it("flags repetitive text", () => {
    const flags = evaluateTextQuality("update update update update update update update update");
    expect(flags.isRepetitive).toBe(true);
  });
});
