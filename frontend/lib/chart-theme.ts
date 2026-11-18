/**
 * Shared chart design tokens and colour assignment.
 *
 * The application keeps its red identity for branding and primary actions,
 * but data visualisation uses a wider categorical palette. Colour assignment
 * is centralised here so the same category (skill, status, company, job
 * family, metric, ...) receives the same colour in every chart. Recharts is
 * only the renderer; it never decides the palette.
 */

/** Ten-colour professional palette used as the primary categorical set. */
export const CHART_PALETTE = {
  red: "#DC2626",
  blue: "#2563EB",
  purple: "#7C3AED",
  teal: "#0D9488",
  orange: "#EA580C",
  green: "#16A34A",
  amber: "#D97706",
  pink: "#DB2777",
  indigo: "#4F46E5",
  cyan: "#0891B2",
} as const;

export type ChartPaletteColor = (typeof CHART_PALETTE)[keyof typeof CHART_PALETTE];

const HEX_COLOR = /^#([\da-f]{6})$/i;

function hexToRgb(color: string): [number, number, number] | null {
  const match = HEX_COLOR.exec(color);
  if (!match?.[1]) return null;
  return [
    Number.parseInt(match[1].slice(0, 2), 16),
    Number.parseInt(match[1].slice(2, 4), 16),
    Number.parseInt(match[1].slice(4, 6), 16),
  ];
}

function interpolateHex(from: string, to: string, ratio: number): string {
  const start = hexToRgb(from);
  const end = hexToRgb(to);
  if (!start || !end) return from;
  const channels = start.map((value, index) =>
    Math.round(value + (end[index]! - value) * ratio)
      .toString(16)
      .padStart(2, "0")
  );
  return `#${channels.join("")}`;
}

function mixHex(color: string, target: string, ratio: number): string {
  return interpolateHex(color, target, ratio);
}

/**
 * Base categorical palette. The first ten entries are the primary palette;
 * the darker/alternate hues extend it deterministically for datasets with
 * more categories than the primary set.
 */
const BASE_CATEGORICAL_COLORS: string[] = [
  CHART_PALETTE.red,
  CHART_PALETTE.blue,
  CHART_PALETTE.purple,
  CHART_PALETTE.teal,
  CHART_PALETTE.orange,
  CHART_PALETTE.green,
  CHART_PALETTE.amber,
  CHART_PALETTE.pink,
  CHART_PALETTE.indigo,
  CHART_PALETTE.cyan,
  "#A21CAF", // fuchsia-700
  "#3F6212", // lime-700
  "#1E40AF", // blue-800
  "#831843", // pink-900
  "#14532D", // green-900
  "#713F12", // yellow-900
  "#164E63", // cyan-900
  "#581C87", // purple-900
  "#7F1D1D", // red-900
  "#365314", // lime-900
  "#BE123C", // rose-700
  "#3730A3", // indigo-800
  "#0F766E", // teal-700
  "#9A3412", // orange-800
];

/**
 * Full categorical palette (base hues, then light and dark variants). Hue
 * order is preserved within each variant group, so neighbouring palette
 * entries remain visibly different. This gives deterministic, distinguishable
 * colours well beyond the ten primary hues.
 */
export const CATEGORICAL_COLORS: string[] = [
  ...BASE_CATEGORICAL_COLORS,
  ...BASE_CATEGORICAL_COLORS.map((color) => mixHex(color, "#FFFFFF", 0.16)),
  ...BASE_CATEGORICAL_COLORS.map((color) => mixHex(color, "#000000", 0.14)),
];

/** Stable order for unlabelled multi-series charts. */
export function seriesColor(index: number): string {
  const length = CATEGORICAL_COLORS.length;
  return CATEGORICAL_COLORS[Math.abs(Math.trunc(index)) % length] ?? CHART_PALETTE.red;
}

function normalizeCategoryKey(value: string | number | null | undefined): string {
  return String(value ?? "")
    .trim()
    .replace(/\s+/g, " ")
    .toLocaleLowerCase();
}

/** Semantic and explicitly requested category colours. Keys are normalised. */
export const CATEGORY_COLOR_OVERRIDES: Readonly<Record<string, string>> = {
  // Top trending skills — explicit, stable mapping requested by the product.
  [normalizeCategoryKey("Python")]: CHART_PALETTE.blue,
  [normalizeCategoryKey("Git")]: CHART_PALETTE.orange,
  [normalizeCategoryKey("Docker")]: CHART_PALETTE.purple,
  [normalizeCategoryKey("AWS")]: CHART_PALETTE.teal,
  [normalizeCategoryKey("SQL")]: CHART_PALETTE.red,
  [normalizeCategoryKey("REST APIs")]: CHART_PALETTE.green,
  [normalizeCategoryKey("Communication")]: CHART_PALETTE.indigo,
  [normalizeCategoryKey("Problem Solving")]: CHART_PALETTE.pink,
  [normalizeCategoryKey("Ownership")]: CHART_PALETTE.amber,
  [normalizeCategoryKey("Attention to Detail")]: CHART_PALETTE.cyan,

  // Application status. One global semantic set: Applied blue, Shortlisted
  // green, Rejected red. Selected keeps teal for the admin placement view
  // (legacy outcome); TPO dashboards never render a Selected stage.
  [normalizeCategoryKey("Applied")]: CHART_PALETTE.blue,
  [normalizeCategoryKey("Shortlisted")]: CHART_PALETTE.green,
  [normalizeCategoryKey("Rejected")]: CHART_PALETTE.red,
  [normalizeCategoryKey("Selected")]: CHART_PALETTE.teal,

  // Five placement domains. Stable across the student radar, TPO breakdowns
  // and any future per-domain chart.
  [normalizeCategoryKey("Quantitative Aptitude")]: CHART_PALETTE.indigo,
  [normalizeCategoryKey("Logical Reasoning")]: CHART_PALETTE.orange,
  [normalizeCategoryKey("Verbal Ability")]: CHART_PALETTE.purple,
  [normalizeCategoryKey("Technical Knowledge")]: CHART_PALETTE.cyan,
  [normalizeCategoryKey("Programming / Problem Solving")]: CHART_PALETTE.pink,

  // User-account roles shown in the admin distribution donut.
  [normalizeCategoryKey("Students")]: CHART_PALETTE.blue,
  [normalizeCategoryKey("Student")]: CHART_PALETTE.blue,
  [normalizeCategoryKey("TPOs")]: CHART_PALETTE.purple,
  [normalizeCategoryKey("TPO")]: CHART_PALETTE.purple,
  [normalizeCategoryKey("Admins")]: CHART_PALETTE.red,
  [normalizeCategoryKey("Admin")]: CHART_PALETTE.red,

  // Admin activity lines.
  [normalizeCategoryKey("New students")]: CHART_PALETTE.blue,
  [normalizeCategoryKey("New drives")]: CHART_PALETTE.purple,
  [normalizeCategoryKey("Applications")]: CHART_PALETTE.orange,

  // Metrics that appear as series keys in more than one chart.
  "industry demand %": CHART_PALETTE.blue,
  "demand": CHART_PALETTE.blue,
  "assessment-demonstrated %": CHART_PALETTE.green,
  "demonstrated": CHART_PALETTE.green,
  "self-reported %": CHART_PALETTE.amber,
  "reported": CHART_PALETTE.amber,
  "posting count": CHART_PALETTE.red,
  "postingcount": CHART_PALETTE.red,
  "company": CHART_PALETTE.purple,
  "job family": CHART_PALETTE.green,
  "jobfamily": CHART_PALETTE.green,
  "year demand": CHART_PALETTE.teal,
  "yeardemand": CHART_PALETTE.teal,
  "trajectory": CHART_PALETTE.orange,
};

/** FNV-1a: small, deterministic and independent of render order. */
function hashCategory(key: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < key.length; index += 1) {
    hash ^= key.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

export function hasCategoryColorOverride(category: string | number | null | undefined): boolean {
  return Object.prototype.hasOwnProperty.call(CATEGORY_COLOR_OVERRIDES, normalizeCategoryKey(category));
}

/**
 * Canonical colour for a category. This function never looks at surrounding
 * data or array position, so Python is blue in every chart that shows it.
 */
export function categoryColor(category: string | number | null | undefined): string {
  const key = normalizeCategoryKey(category);
  const override = CATEGORY_COLOR_OVERRIDES[key];
  if (override) return override;
  if (key.length === 0) return CHART_PALETTE.red;
  const index = hashCategory(key) % CATEGORICAL_COLORS.length;
  return CATEGORICAL_COLORS[index] ?? CHART_PALETTE.red;
}

/** RGB distance used only to keep adjacent bars/series visually separable. */
export function chartColorDistance(first: string, second: string): number {
  const a = hexToRgb(first);
  const b = hexToRgb(second);
  if (!a || !b) return Number.POSITIVE_INFINITY;
  return Math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2);
}

/** Colours considered too similar when they touch in a chart. */
export const MIN_ADJACENT_COLOR_DISTANCE = 110;

/**
 * Deterministic colours for an ordered categorical dataset.
 *
 * Canonical overrides always win. For generated categories the function
 * starts from the stable category colour, then picks the next palette entry
 * only if it would sit too close to one of the two previous bars. Repeated
 * categories inside the same dataset keep one colour.
 */
export function assignCategoryColors(
  categories: Array<string | number | null | undefined>
): string[] {
  const chosenByKey = new Map<string, string>();
  return categories.map((category, index) => {
    const key = normalizeCategoryKey(category);
    const cached = chosenByKey.get(key);
    if (cached) return cached;

    const baseColor = categoryColor(category);
    let chosen = baseColor;

    if (!hasCategoryColorOverride(category)) {
      const blocked = colorsBefore(categories, chosenByKey, index);
      if (blocked.some((color) => chartColorDistance(color, baseColor) < MIN_ADJACENT_COLOR_DISTANCE)) {
        const baseIndex = CATEGORICAL_COLORS.indexOf(baseColor);
        for (let step = 1; step < CATEGORICAL_COLORS.length; step += 1) {
          const candidate =
            CATEGORICAL_COLORS[(baseIndex + step + CATEGORICAL_COLORS.length) % CATEGORICAL_COLORS.length]!;
          if (blocked.every((color) => chartColorDistance(color, candidate) >= MIN_ADJACENT_COLOR_DISTANCE)) {
            chosen = candidate;
            break;
          }
        }
      }
    }

    chosenByKey.set(key, chosen);
    return chosen;
  });
}

function colorsBefore(
  categories: Array<string | number | null | undefined>,
  chosenByKey: Map<string, string>,
  index: number
): string[] {
  const colors: string[] = [];
  for (let position = Math.max(0, index - 2); position < index; position += 1) {
    const key = normalizeCategoryKey(categories[position]);
    const color = chosenByKey.get(key);
    if (color) colors.push(color);
  }
  return colors;
}

/**
 * Sequential colour for an ordered numeric axis (for example year-wise
 * demand). Unlike categorical colour this encodes progression, not identity.
 */
export function sequentialColor(
  index: number,
  count: number,
  from: string = CHART_PALETTE.teal,
  to: string = CHART_PALETTE.cyan
): string {
  if (count <= 1) return from;
  const safeIndex = Math.min(count - 1, Math.max(0, index));
  return interpolateHex(from, to, safeIndex / (count - 1));
}

/** Semantic series colours — reused by every chart that shows the same metric. */
export const SERIES_COLORS = {
  demand: CHART_PALETTE.blue,
  demonstrated: CHART_PALETTE.green,
  reported: CHART_PALETTE.amber,
  applied: CHART_PALETTE.blue,
  shortlisted: CHART_PALETTE.green,
  rejected: CHART_PALETTE.red,
  postingCount: CHART_PALETTE.red,
  company: CHART_PALETTE.purple,
  jobFamily: CHART_PALETTE.green,
  yearDemand: CHART_PALETTE.teal,
  trajectory: CHART_PALETTE.orange,
  newStudents: CHART_PALETTE.blue,
  newDrives: CHART_PALETTE.purple,
  applications: CHART_PALETTE.orange,
} as const;

/** Backwards-compatible stable order for up to four compared lines. */
export const HISTORICAL_LINE_COLORS: string[] = CATEGORICAL_COLORS.slice(0, 4);

export const CHART_AXIS_STYLE = {
  fill: "#64748B",
  fontSize: 12,
} as const;

export const CHART_GRID_STROKE = "#E2E8F0";
export const CHART_CURSOR_FILL = "rgba(15, 23, 42, 0.05)";

export const CHART_TOOLTIP_STYLE = {
  borderRadius: 10,
  border: `1px solid ${CHART_GRID_STROKE}`,
  boxShadow: "0 8px 24px rgba(15, 23, 42, 0.1)",
  fontSize: 12,
} as const;

export const DEFAULT_CHART_MARGIN = { top: 8, right: 12, left: 4, bottom: 8 } as const;

/** Recharts axis-label object with the shared style applied. */
export function chartAxisLabel(value: string, position: "insideBottom" | "insideLeft" = "insideBottom") {
  return {
    value,
    position,
    fill: CHART_AXIS_STYLE.fill,
    fontSize: CHART_AXIS_STYLE.fontSize,
    offset: position === "insideBottom" ? -14 : 12,
  };
}

/** Tick formatter for 0-100 percentage axes. */
export function percentTick(value: number): string {
  return `${value}%`;
}
