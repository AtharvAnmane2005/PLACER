/**
 * Shared numerical and date formatting.
 *
 * Every number shown in cards, tables, charts and generated insights should
 * go through these helpers so a metric means the same thing everywhere.
 * Values are never rounded before they reach this layer.
 */

const DISPLAY_LOCALE = "en-US";
const CURRENCY_LOCALE = "en-IN";

function finite(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function numberFormat(digits: number) {
  return new Intl.NumberFormat(DISPLAY_LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Counts: 1250 -> "1,250". */
export function formatCount(value: number | null | undefined, fallback = "—"): string {
  return finite(value) ? numberFormat(0).format(value) : fallback;
}

/** Fixed-precision decimal: 76.25 -> "76.25". */
export function formatDecimal(
  value: number | null | undefined,
  digits = 2,
  fallback = "—"
): string {
  return finite(value) ? numberFormat(digits).format(value) : fallback;
}

/** Percentages are already on a 0-100 scale: 78.5 -> "78.50%". */
export function formatPercent(
  value: number | null | undefined,
  digits = 2,
  fallback = "N/A"
): string {
  return finite(value) ? `${numberFormat(digits).format(value)}%` : fallback;
}

/** A 0-1 ratio expressed as a percentage: 0.854 -> "85.40%". */
export function formatRatioAsPercent(
  ratio: number | null | undefined,
  digits = 2,
  fallback = "N/A"
): string {
  return finite(ratio) ? formatPercent(ratio * 100, digits, fallback) : fallback;
}

/** Signed change for charts/tooltips: 12.5 -> "+12.5%". */
export function formatSignedPercent(
  value: number | null | undefined,
  digits = 1,
  fallback = "N/A"
): string {
  if (!finite(value)) return fallback;
  const formatted = numberFormat(digits).format(Math.abs(value));
  return `${value > 0 ? "+" : value < 0 ? "-" : ""}${formatted}%`;
}

/** Score out of a known maximum: 76.25, 100 -> "76.25/100". */
export function formatScore(
  value: number | null | undefined,
  maximum = 100,
  digits = 2
): string {
  return `${formatDecimal(value, digits)}/${formatCount(maximum)}`;
}

/** Duration in seconds -> "30 minutes"; zero -> "0 minutes". */
export function formatDuration(totalSeconds: number | null | undefined): string {
  if (!finite(totalSeconds)) return "—";
  const minutes = Math.max(0, Math.round(totalSeconds / 60));
  return `${formatCount(minutes)} minute${minutes === 1 ? "" : "s"}`;
}

/** Indian rupee formatting where a currency is actually applicable. */
export function formatCurrencyINR(value: number | null | undefined, fallback = "—"): string {
  if (!finite(value)) return fallback;
  return new Intl.NumberFormat(CURRENCY_LOCALE, {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

/** Application-wide date format: "Nov 18, 2026". */
export function formatDate(value: string | number | Date | null | undefined, fallback = "—"): string {
  if (value == null || value === "") return fallback;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, { dateStyle: "medium" }).format(date);
}

/** Application-wide date + time format. */
export function formatDateTime(
  value: string | number | Date | null | undefined,
  fallback = "—"
): string {
  if (value == null || value === "") return fallback;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

/**
 * Month bucket key ("YYYY-MM") -> "Jan 2026". Used by the dashboard monthly
 * trend axes and tooltips so the backend can keep a sortable key.
 */
export function formatMonthKey(value: string | null | undefined, fallback = "—"): string {
  if (!value) return fallback;
  const match = /^(\d{4})-(\d{2})$/.exec(value);
  if (!match) return value;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, 1);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, { month: "short", year: "numeric" }).format(date);
}
