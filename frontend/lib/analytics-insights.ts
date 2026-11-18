/**
 * Reusable, data-driven analytics helpers.
 *
 * These functions operate only on values supplied by the API. They never
 * invent a data point, never treat a missing period as zero, and never claim
 * sustained growth unless every observed interval increased.
 */

import { formatDecimal, formatPercent, formatSignedPercent } from "@/lib/format";

export interface TrendPoint {
  /** Chronological key: a year, ISO date string, or label. */
  period: string | number;
  /** Null means "no comparable value", never zero. */
  value: number | null;
}

export type TrendDirection =
  | "increasing"
  | "decreasing"
  | "stable"
  | "fluctuating"
  | "insufficient";

export interface TrendAnalysis {
  direction: TrendDirection;
  /** A sentence that matches the observed pattern exactly. */
  description: string;
  observedPeriods: number;
  missingPeriods: number;
  firstValue: number | null;
  lastValue: number | null;
  overallChange: number | null;
  overallChangePct: number | null;
  changeFromPrevious: number | null;
  changeFromPreviousPct: number | null;
  increasedInEveryPeriod: boolean;
  decreasedInEveryPeriod: boolean;
  hasFluctuations: boolean;
  isReliable: boolean;
}

export interface TrendOptions {
  /** Relative band within which a metric is described as stable. Default 5%. */
  stableTolerancePct?: number;
  /** Minimum non-null observations required for a conclusion. Default 2. */
  minPeriods?: number;
  /** Full set of expected periods; missing ones are counted, not zero-filled. */
  expectedPeriods?: Array<string | number>;
  /** Noun used in the generated sentence, e.g. "Average score". */
  subject?: string;
  /** Whether the latest period covers a partial window (mixed comparisons). */
  hasPartialLatestPeriod?: boolean;
}

function comparePeriods(a: string | number, b: string | number): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

/** Percentage change with safe zero-baseline handling. Returns null if unknown. */
export function percentageChange(oldValue: number | null, newValue: number | null): number | null {
  if (oldValue == null || newValue == null || !Number.isFinite(oldValue) || !Number.isFinite(newValue)) {
    return null;
  }
  if (oldValue === 0) return null;
  return ((newValue - oldValue) / Math.abs(oldValue)) * 100;
}

/** Arithmetic mean of the supplied observations; null when there are none. */
export function arithmeticMean(values: Array<number | null | undefined>): number | null {
  const valid = values.filter((value): value is number => value != null && Number.isFinite(value));
  if (valid.length === 0) return null;
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

/** Completion rate with a zero-denominator guard, on a 0-100 scale. */
export function completionRate(completed: number, total: number): number | null {
  if (!Number.isFinite(total) || total <= 0) return null;
  return (completed / total) * 100;
}

/** Actual maximum of a dataset, with deterministic tie-breaking. */
export function highestBy<T>(
  items: T[],
  valueOf: (item: T) => number | null,
  labelOf: (item: T) => string
): T | null {
  let best: T | null = null;
  let bestValue = Number.NEGATIVE_INFINITY;
  for (const item of items) {
    const value = valueOf(item);
    if (value == null || !Number.isFinite(value)) continue;
    if (value > bestValue || (value === bestValue && best != null && labelOf(item) < labelOf(best))) {
      best = item;
      bestValue = value;
    }
  }
  return best;
}

/** Actual minimum of a dataset, with deterministic tie-breaking. */
export function lowestBy<T>(
  items: T[],
  valueOf: (item: T) => number | null,
  labelOf: (item: T) => string
): T | null {
  let best: T | null = null;
  let bestValue = Number.POSITIVE_INFINITY;
  for (const item of items) {
    const value = valueOf(item);
    if (value == null || !Number.isFinite(value)) continue;
    if (value < bestValue || (value === bestValue && best != null && labelOf(item) < labelOf(best))) {
      best = item;
      bestValue = value;
    }
  }
  return best;
}

/**
 * Analyse a time series and describe it accurately.
 *
 * Rules:
 * - periods are sorted chronologically and missing periods are counted but
 *   never filled with fabricated zeros;
 * - deltas are calculated between consecutive non-null observations;
 * - "increased/decreased in every observed period" requires every delta to
 *   have that sign and at least three observations (with two, the statement
 *   is deliberately downgraded to "compared with the previous period");
 * - a change of sign is reported as a fluctuation, never as steady growth;
 * - "stable" requires the overall change to stay within the tolerance band
 *   without significant fluctuations;
 * - a partial latest period downgrades sustained-growth language.
 */
export function analyzeTrend(points: TrendPoint[], options: TrendOptions = {}): TrendAnalysis {
  const {
    stableTolerancePct = 5,
    minPeriods = 2,
    expectedPeriods,
    subject = "The metric",
    hasPartialLatestPeriod = false,
  } = options;

  const byPeriod = new Map<string | number, number | null>();
  for (const point of points) byPeriod.set(point.period, point.value);

  const orderedPeriods =
    expectedPeriods && expectedPeriods.length > 0
      ? [...new Set(expectedPeriods)]
      : [...byPeriod.keys()];
  orderedPeriods.sort(comparePeriods);

  const missingPeriods = expectedPeriods
    ? expectedPeriods.filter((period) => byPeriod.get(period) == null).length
    : points.filter((point) => point.value == null).length;

  const observations = orderedPeriods
    .map((period) => byPeriod.get(period) ?? null)
    .filter((value): value is number => value != null && Number.isFinite(value));

  const firstValue = observations[0] ?? null;
  const lastValue = observations[observations.length - 1] ?? null;
  const overallChange = firstValue != null && lastValue != null ? lastValue - firstValue : null;
  const overallChangePct = percentageChange(firstValue, lastValue);
  const previousValue = observations.length >= 2 ? observations[observations.length - 2]! : null;
  const changeFromPrevious =
    previousValue != null && lastValue != null ? lastValue - previousValue : null;
  const changeFromPreviousPct = percentageChange(previousValue, lastValue);

  const deltas: number[] = [];
  for (let index = 1; index < observations.length; index += 1) {
    deltas.push(observations[index]! - observations[index - 1]!);
  }
  const positive = deltas.filter((delta) => delta > 0).length;
  const negative = deltas.filter((delta) => delta < 0).length;
  const increasedInEveryPeriod = deltas.length > 0 && positive === deltas.length;
  const decreasedInEveryPeriod = deltas.length > 0 && negative === deltas.length;
  const hasFluctuations = positive > 0 && negative > 0;

  const reliable = observations.length >= minPeriods;
  let direction: TrendDirection = "insufficient";
  let description = "Insufficient data to determine a reliable trend.";

  if (reliable && overallChange != null) {
    const withinTolerance =
      overallChangePct != null
        ? Math.abs(overallChangePct) <= stableTolerancePct
        : Math.abs(overallChange) <= stableTolerancePct;

    if (increasedInEveryPeriod && !hasPartialLatestPeriod) {
      direction = "increasing";
      description =
        observations.length >= 3
          ? `${subject} increased in every observed period, from ${formatDecimal(firstValue, 1)} to ${formatDecimal(lastValue, 1)} (${formatSignedPercent(overallChangePct)} overall).`
          : `${subject} increased compared with the previous period (${formatSignedPercent(changeFromPreviousPct)}).`;
    } else if (decreasedInEveryPeriod && !hasPartialLatestPeriod) {
      direction = "decreasing";
      description =
        observations.length >= 3
          ? `${subject} decreased in every observed period, from ${formatDecimal(firstValue, 1)} to ${formatDecimal(lastValue, 1)} (${formatSignedPercent(overallChangePct)} overall).`
          : `${subject} decreased compared with the previous period (${formatSignedPercent(changeFromPreviousPct)}).`;
    } else if (hasFluctuations) {
      direction = "fluctuating";
      const ending = overallChange > 0 ? "ended higher" : overallChange < 0 ? "ended lower" : "ended at the starting value";
      description = `${subject} fluctuated during the observed period and ${ending} (${formatSignedPercent(overallChangePct)} overall).`;
    } else if (withinTolerance) {
      direction = "stable";
      description = `${subject} remained relatively stable (${formatPercent(Math.abs(overallChangePct ?? 0), 1)} net change).`;
    } else if (overallChange > 0) {
      direction = "increasing";
      description = `${subject} increased overall (${formatSignedPercent(overallChangePct)}), with a partial latest period. Changes are not directly comparable across all periods.`;
    } else {
      direction = "decreasing";
      description = `${subject} decreased overall (${formatSignedPercent(overallChangePct)}), with a partial latest period. Changes are not directly comparable across all periods.`;
    }
  }

  return {
    direction,
    description,
    observedPeriods: observations.length,
    missingPeriods,
    firstValue,
    lastValue,
    overallChange,
    overallChangePct,
    changeFromPrevious,
    changeFromPreviousPct,
    increasedInEveryPeriod: increasedInEveryPeriod && !hasPartialLatestPeriod,
    decreasedInEveryPeriod: decreasedInEveryPeriod && !hasPartialLatestPeriod,
    hasFluctuations,
    isReliable: reliable,
  };
}

/** Human-readable summary of a completion rate without implying a trend. */
export function describeCompletion(completed: number, total: number, subject = "Assessments"): string {
  const rate = completionRate(completed, total);
  if (rate == null) return "Insufficient data to determine a completion rate.";
  return `${formatCountSafe(completed)} of ${formatCountSafe(total)} ${subject.toLowerCase()} completed (${formatPercent(rate, 1)}).`;
}

function formatCountSafe(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}
