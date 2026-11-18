/**
 * Types for the TPO Market Insights dashboard (Trending Skills & Company
 * Requirements).
 *
 * Mirrors the Phase 3 backend Pydantic response models exactly
 * (backend/app/models/market.py). Field names, nullability and enum values
 * must not diverge — the backend contract is the source of truth.
 *
 * Note: the backend serialises `dict[int, int]` yearly maps with JSON string
 * keys (e.g. {"2023": 45}), so they are `Record<string, number>` here.
 */

export type TrendClassification = "rising" | "declining" | "stable" | "emerging";

export type MarketSort = "trending" | "demand";

export interface MarketPeriodInfo {
  year: number;
  start_month: number;
  end_month: number;
  label: string;
}

/** Whether the figures are demo data, imported real postings, or both. */
export type MarketDataOrigin = "mock" | "real" | "mixed";

/** Provenance of one market-data source present in the dataset. */
export interface MarketSourceInfo {
  id: string;
  label: string;
  is_mock: boolean;
  posting_count: number;
  latest_posted_at: string | null;
  imported_at: string | null;
  license: string | null;
  homepage: string | null;
}

export interface MarketMeta {
  source: string;
  dataset_version: string;
  is_mock_data: boolean;
  comparison_period: string;
  is_partial_year: boolean;
  disclaimer: string;
  current_period: MarketPeriodInfo | null;
  previous_period: MarketPeriodInfo | null;
  comparison_comparable: boolean;
  filtered_years: number[];
  /** Exact source ids that produced the filtered figures. */
  sources: string[];
  data_origin: MarketDataOrigin;
  latest_import_at: string | null;
}

export interface MarketSkillDemand {
  name: string;
  slug: string;
  category: string | null;
  posting_count: number;
  demand_pct: number;
}

export interface MarketSummary {
  total_postings: number;
  company_count: number;
  distinct_skill_count: number;
  most_demanded_skill: MarketSkillDemand | null;
  yoy_posting_growth_pct: number | null;
}

export interface TrendingSkill {
  name: string;
  slug: string;
  category: string | null;
  is_technical: boolean;
  posting_count: number;
  demand_pct: number;
  trend_score: number;
  trend: TrendClassification | null;
  yoy_growth_pct: number | null;
  current_period_count: number;
  previous_period_count: number;
  yearly_counts: Record<string, number>;
  yearly_demand_pct: Record<string, number>;
}

export interface YearlySkillDemand {
  year: number;
  /** Calendar-year total (may be a full year while the latest year is partial). */
  posting_count: number;
  /** Calendar-year demand share, matching `posting_count`. */
  demand_pct: number;
  /** Postings inside the comparable window used by `yoy_growth_pct`. */
  window_posting_count: number;
  /** Demand share inside the comparable window used by `yoy_growth_pct`. */
  window_demand_pct: number;
  yoy_growth_pct: number | null;
}

export interface HistoricalSkillTrend {
  name: string;
  slug: string;
  category: string | null;
  years: YearlySkillDemand[];
}

export interface EmergingSkill {
  name: string;
  slug: string;
  category: string | null;
  current_period_count: number;
  current_period_demand_pct: number;
  previous_period_count: number;
  trend: "emerging";
}

export interface CompanyMarketAnalytics {
  company_name: string;
  company_slug: string;
  industry: string;
  posting_count: number;
  posting_share_pct: number;
  top_skills: MarketSkillDemand[];
  yearly_counts: Record<string, number>;
}

export interface JobFamilyMarketAnalytics {
  job_family: string;
  posting_count: number;
  posting_share_pct: number;
  top_skills: MarketSkillDemand[];
  yearly_counts: Record<string, number>;
}

export interface CompanyFilterOption {
  slug: string;
  name: string;
}

export interface MarketFiltersResponse {
  years: number[];
  /** Capped list of companies (highest posting counts first). */
  companies: CompanyFilterOption[];
  /** True number of distinct companies; may exceed `companies.length`. */
  company_total: number;
  job_families: string[];
  /** Capped list of locations (highest posting counts first). */
  locations: string[];
  /** True number of distinct locations; may exceed `locations.length`. */
  location_total: number;
  skill_categories: string[];
  /** Every source present in the collection, for an honest source switch. */
  sources: MarketSourceInfo[];
}

export interface MarketAnalyticsResponse {
  meta: MarketMeta;
  summary: MarketSummary;
  trending_skills: TrendingSkill[];
  historical_trends: HistoricalSkillTrend[];
  emerging_skills: EmergingSkill[];
  companies: CompanyMarketAnalytics[];
  job_families: JobFamilyMarketAnalytics[];
}

/** Query parameters accepted by GET /api/v1/analytics/tpo/market. */
export interface MarketAnalyticsParams {
  /** "mock", "real", "all" or an exact source id; omitted = default group. */
  source?: string;
  year_from?: number;
  year_to?: number;
  company?: string;
  job_family?: string;
  location?: string;
  skill_category?: string;
  technical_only?: boolean;
  sort?: MarketSort;
  limit?: number;
}

// ---------------------------------------------------------------------------
// Phase 5 — entity comparison (GET /api/v1/analytics/tpo/market/comparison)
// ---------------------------------------------------------------------------

export type ComparisonDimension = "company" | "job_family";

/** Full analytics for ONE compared entity (a company or a job family). */
export interface ComparisonEntityAnalytics {
  entity_key: string;
  entity_label: string;
  industry: string | null;
  posting_count: number;
  posting_share_pct: number;
  tech_skill_instances: number;
  soft_skill_instances: number;
  tech_share_pct: number;
  soft_share_pct: number;
  yearly_counts: Record<string, number>;
  /** Every skill the entity requires — NOT limited to a top-10 slice. */
  skills: TrendingSkill[];
}

export interface MarketComparisonResponse {
  meta: MarketMeta;
  dimension: ComparisonDimension;
  entities: ComparisonEntityAnalytics[];
}

/** Query parameters accepted by GET /api/v1/analytics/tpo/market/comparison. */
export interface MarketComparisonParams {
  dimension: ComparisonDimension;
  /** Comma-joined entity keys (company slugs or job-family names). */
  entities: string;
  /** Same source group as the dashboard, so comparison matches the page. */
  source?: string;
  year_from?: number;
  year_to?: number;
  /** Posting filter applied when dimension === "company". */
  job_family?: string;
  /** Posting filter applied when dimension === "job_family". */
  company?: string;
  location?: string;
}
