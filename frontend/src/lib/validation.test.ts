import { describe, expect, it } from "vitest";
import { decodePolyline } from "./polyline";
import { parseLoad, validate } from "./validation";

const now = new Date("2026-01-10T12:00:00Z");
const ok = { originText: "Chicago", destText: "Dallas", departure: "2026-01-10T15:00", load: "38,000" };

describe("validate", () => {
  it("accepts a valid form", () => {
    expect(validate(ok, true, true, now)).toEqual({});
  });
  it("flags missing places and load", () => {
    const e = validate({ ...ok, originText: "", destText: " ", load: "" }, false, false, now);
    expect(e.origin && e.destination && e.load).toBeTruthy();
  });
  it("rejects overweight, negative and junk loads", () => {
    expect(validate({ ...ok, load: "95000" }, true, true, now).load).toMatch(/Maximum/);
    expect(validate({ ...ok, load: "abc" }, true, true, now).load).toBeTruthy();
    expect(validate({ ...ok, load: "-5" }, true, true, now).load).toBeTruthy();
  });
  it("rejects past and far-future departures", () => {
    expect(validate({ ...ok, departure: "2025-01-01T00:00" }, true, true, now).departure).toMatch(/past/);
    expect(validate({ ...ok, departure: "2026-03-01T00:00" }, true, true, now).departure).toMatch(/14 days/);
  });
  it("parses formatted weights", () => {
    expect(parseLoad("38,000")).toBe(38000);
  });
});

describe("decodePolyline", () => {
  it("decodes the classic Google example at precision 5", () => {
    const pts = decodePolyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", 5);
    expect(pts[0][1]).toBeCloseTo(38.5, 4);
    expect(pts[0][0]).toBeCloseTo(-120.2, 4);
    expect(pts).toHaveLength(3);
  });
});
