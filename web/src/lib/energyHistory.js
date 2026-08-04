// Append one sample (an array of per-gate energies) to a rolling history, trimming the oldest so
// it never grows past `maxLen`. Pure + non-mutating so it's unit-testable without a DOM -- the
// EnergyTimeChart's ring buffer is built on this.
export function pushSample(history, sample, maxLen) {
  const next = [...history, sample];
  if (next.length > maxLen) {
    return next.slice(next.length - maxLen);
  }
  return next;
}
