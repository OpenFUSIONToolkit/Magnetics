import { expect, test } from "vitest";
import { loopSegment2d } from "./sensorGeometry";

const base = { r: 2.0, z: 0.5, length: 0.4 };

test("0° tilt lies along R (horizontal)", () => {
  const s = loopSegment2d({ ...base, tilt: 0 });
  expect(s.x[0]).toBeCloseTo(1.8);
  expect(s.x[1]).toBeCloseTo(2.2);
  expect(s.y[0]).toBeCloseTo(0.5);
  expect(s.y[1]).toBeCloseTo(0.5);
});

test("90° tilt lies along Z (vertical)", () => {
  const s = loopSegment2d({ ...base, tilt: 90 });
  expect(s.x[0]).toBeCloseTo(2.0);
  expect(s.x[1]).toBeCloseTo(2.0);
  expect(s.y[0]).toBeCloseTo(0.3);
  expect(s.y[1]).toBeCloseTo(0.7);
});

test("segment is symmetric about the sensor centre", () => {
  const s = loopSegment2d({ ...base, tilt: 37 });
  expect((s.x[0] + s.x[1]) / 2).toBeCloseTo(base.r);
  expect((s.y[0] + s.y[1]) / 2).toBeCloseTo(base.z);
});
