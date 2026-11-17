import { describe, expect, it } from "vitest";
import { delayBand, formatClock, formatDelay, formatDuration, modeLabel, percent, sentenceCase } from "./format";

describe("delayBand", () => {
  it("puts the band edges inside the band, as the API does", () => {
    expect(delayBand(-61)).toBe("early");
    expect(delayBand(-60)).toBe("within");
    expect(delayBand(0)).toBe("within");
    expect(delayBand(300)).toBe("within");
    expect(delayBand(301)).toBe("late");
  });

  it("uses the limits it is given", () => {
    expect(delayBand(200, { earlySeconds: 30, lateSeconds: 120 })).toBe("late");
    expect(delayBand(-40, { earlySeconds: 30, lateSeconds: 120 })).toBe("early");
  });
});

describe("formatDelay", () => {
  it("always says which way", () => {
    expect(formatDelay(240)).toBe("4 min late");
    expect(formatDelay(-120)).toBe("2 min early");
    expect(formatDelay(20)).toBe("on time");
    expect(formatDelay(-29)).toBe("on time");
  });

  it("does not turn a missing prediction into a number", () => {
    expect(formatDelay(null)).toBe("no prediction");
    expect(formatDelay(undefined)).toBe("no prediction");
  });
});

describe("formatDuration", () => {
  it("chooses a readable unit", () => {
    expect(formatDuration(14)).toBe("14 s");
    expect(formatDuration(89)).toBe("89 s");
    expect(formatDuration(60)).toBe("1 min");
    expect(formatDuration(120)).toBe("2 min");
    expect(formatDuration(3600)).toBe("60 min");
    expect(formatDuration(7500)).toBe("2 h 5 min");
    expect(formatDuration(7200)).toBe("2 h");
    expect(formatDuration(-5)).toBe("0 s");
  });
});

describe("formatClock", () => {
  it("shows Brisbane time whatever the viewer's time zone", () => {
    expect(formatClock("2026-11-16T09:03:20+10:00")).toBe("09:03");
    expect(formatClock("2026-11-15T23:03:20Z", true)).toBe("09:03:20");
  });

  it("shows a dash when there is no time", () => {
    expect(formatClock(null)).toBe("–");
  });
});

describe("small helpers", () => {
  it("percent", () => {
    expect(percent(112, 1046)).toBe("11%");
    expect(percent(0, 0)).toBe("–");
  });

  it("names modes and codes for people", () => {
    expect(modeLabel("rail")).toBe("Train");
    expect(modeLabel(null)).toBe("Unknown");
    expect(sentenceCase("stop_moved")).toBe("Stop moved");
  });
});
