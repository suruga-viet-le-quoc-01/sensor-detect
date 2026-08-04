import { describe, expect, it } from "vitest";

import { pushSample } from "../src/lib/energyHistory.js";

describe("pushSample", () => {
  it("appends the first sample to an empty history", () => {
    const result = pushSample([], [1, 2, 3], 5);
    expect(result).toEqual([[1, 2, 3]]);
  });

  it("appends without trimming while under maxLen", () => {
    const result = pushSample([[1], [2]], [3], 5);
    expect(result).toEqual([[1], [2], [3]]);
  });

  it("drops the oldest samples once past maxLen", () => {
    const result = pushSample([[1], [2], [3]], [4], 3);
    expect(result).toEqual([[2], [3], [4]]);
  });

  it("does not mutate the input history", () => {
    const history = [[1], [2]];
    pushSample(history, [3], 5);
    expect(history).toEqual([[1], [2]]);
  });
});
