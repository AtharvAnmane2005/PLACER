/**
 * Three-band performance severity used across the Student dashboard.
 *
 * The bands mirror the backend's mastery thresholds
 * (`student_insights_service.CRITICAL_MASTERY_THRESHOLD = 35` and
 * `WEAK_MASTERY_THRESHOLD = 50`) so a skill is described the same way
 * everywhere it appears. Only three colours are used:
 *
 *   critical  -> red
 *   moderate  -> amber
 *   good      -> green
 *
 * These are display helpers only — they never influence a score, mastery
 * calculation or any assessment logic.
 */
export type SeverityBand = "critical" | "moderate" | "good";

export const SEVERITY_THRESHOLDS = {
  /** Below this mastery a skill is critical. */
  critical: 35,
  /** Below this mastery (but at/above `critical`) a skill is moderate. */
  moderate: 50,
} as const;

/** Derive a band from a mastery percentage (used where no severity is sent). */
export function severityBandFromMastery(masteryPct: number): SeverityBand {
  if (masteryPct < SEVERITY_THRESHOLDS.critical) return "critical";
  if (masteryPct < SEVERITY_THRESHOLDS.moderate) return "moderate";
  return "good";
}

/**
 * Collapse the backend's four-way severity enum into the three UI bands.
 * `weak` and `watch` both describe skills that are not yet satisfactory, so
 * they share the amber band; `ok` is the green band.
 */
export function severityBandFromStatus(
  status: "critical" | "weak" | "watch" | "ok"
): SeverityBand {
  if (status === "critical") return "critical";
  if (status === "weak" || status === "watch") return "moderate";
  return "good";
}

/** Solid bar colour per band, aligned with the semantic theme tokens. */
export const SEVERITY_COLOR: Record<SeverityBand, string> = {
  critical: "hsl(var(--destructive))",
  moderate: "hsl(var(--warning))",
  good: "hsl(var(--success))",
};

/** Tinted pill classes per band — the same colour as the matching bar. */
export const SEVERITY_BADGE_CLASS: Record<SeverityBand, string> = {
  critical: "border-transparent bg-destructive/10 text-destructive",
  moderate: "border-transparent bg-warning/10 text-warning",
  good: "border-transparent bg-success/10 text-success",
};

/** Convenience for bars that only have a mastery percentage. */
export function severityColorFromMastery(masteryPct: number): string {
  return SEVERITY_COLOR[severityBandFromMastery(masteryPct)];
}
