"""TPO market analytics for the Trending Skills & Company Requirements dashboard.

Reads ONLY the job-market dataset collections (``job_market_postings`` +
``market_skill_catalog``) — never ``placement_drives`` or any other operational
placement collection — so market data can never inflate (or be inflated by)
live placement statistics.

Source honesty
    The dataset can contain the curated fictional demo rows (``source="mock"``)
    and genuinely imported public postings (``source="remoteok"``,
    ``source="arbeitnow"``, ...). Mock and real rows are different populations
    and are never silently combined: the default view uses the demo dataset
    when it exists (preserving the historical trend series), and callers can
    select ``source="real"`` (all non-mock rows), ``source="mock"`` or one
    exact source id. Every response reports the exact ``sources`` behind its
    numbers, whether the origin is demo/real/mixed, and a disclaimer that
    matches that origin. A mixed view is possible but explicitly labelled.

Comparison window
    The window is derived from DATA COVERAGE, not a hardcoded calendar
    constant: the end month is the highest month present in the latest
    filtered year (capped by the previous year's coverage), so postings dated
    in November or December are counted instead of silently dropped. The
    coverage map is computed over the whole source population before the
    user's year/company filters are applied, so narrowing a filter cannot
    shrink the window and manufacture a fake trend.

Trend math (single source of truth for every section of the response):

Demand percentage
    ``demand_pct = (distinct postings requiring the skill / total filtered
    postings) * 100`` — one shared denominator per response. A posting is
    counted at most once per skill: Phase 2 guarantees per-posting skill lists
    are duplicate-free and the aggregator counts list membership once per
    posting.

Year-over-year growth
    ``growth = (current - previous) / previous * 100``, computed between
    COMPARABLE windows. When the latest filtered year is the dataset's partial
    year (2026, January-November), both the current and previous windows are
    January-November — never full-2026 vs full-2025. Any other latest year
    compares full calendar years. The historical series uses the SAME basis for
    every year (``window_posting_count`` / ``window_demand_pct``) so a chart of
    that series always moves in the same direction as its growth figure.
    ``previous == 0`` yields ``None`` (handled by the emerging classification),
    never a ZeroDivisionError.

Trend score
    Weighted mean of the skill's year-wise DEMAND SHARES (percentages of that
    year's postings, not raw counts)::

        score = sum(w(year) * demand_pct(skill, year))

    with calendar weights 0.40, 0.30, 0.20, 0.10 by offset from the latest
    filtered year, normalised over the years present in the filtered
    population. If every present year is older than the 4-year window the
    weights fall back to uniform.

Classification
    previous == 0 and current > 0 -> "emerging"
    growth >= +10%                -> "rising"
    growth <= -10%                -> "declining"
    otherwise                     -> "stable"

    A skill with no comparable previous period (the previous window has no
    postings after filtering, e.g. the range or another filter excluded it)
    gets ``None`` — a skill must never be labelled "emerging" merely because a
    filter excluded the period it used to appear in.

Filter semantics
    ``year_from/year_to/company/job_family/location`` filter the POSTING
    population (the shared demand-percentage denominator). ``skill_category``
    and ``technical_only`` narrow which SKILLS are analysed; they never change
    the posting denominator, and they may be combined (intersection). The
    same filtered population feeds the summary, trending, historical,
    emerging, company and job-family sections.

Comparison endpoint (``dimension`` = company | job_family)
    One method serves company-to-company and job-family-to-job-family
    comparisons. The dimension's own filter is REPLACED by the entity
    selection (comparing companies ignores the single-company filter;
    comparing families ignores the single-family filter); every other
    posting filter (year range, location, and the opposite dimension's
    filter) still applies. Skill-scope filters never apply: comparisons
    always analyse all skill types so the technical/soft split is visible.
    Each entity gets the SAME trend math as the dashboard (window rules,
    classification, trend score) but with the entity's own postings as the
    demand denominator, and entity-level comparability (an entity whose
    previous comparable window has no postings reports ``trend=None``,
    never a fake classification). ``posting_share_pct`` is the entity's
    share of the whole filtered population, not of the selected group.

Performance
    One projected find (aggregate-level fields only — no descriptions or JD
    text) bounded at ``_MAX_POSTINGS`` plus one small catalog read; all
    aggregation is a single in-memory pass over the filtered rows.
"""
import calendar
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.market import (
    MARKET_DATASET_VERSION,
    ComparisonEntityAnalytics,
    CompanyFilterOption,
    CompanyMarketAnalytics,
    EmergingSkill,
    HistoricalSkillTrend,
    JobFamilyMarketAnalytics,
    MarketAnalyticsResponse,
    MarketComparisonResponse,
    MarketFiltersResponse,
    MarketMeta,
    MarketPeriodInfo,
    MarketSkillDemand,
    MarketSourceInfo,
    MarketSummary,
    TrendingSkill,
    YearlySkillDemand,
)
from app.repositories.job_posting_repository import (
    JobMarketPostingRepository,
    MarketSkillCatalogRepository,
)
from app.services.market_sources import source_attribution, source_definition

logger = logging.getLogger(__name__)

# Bounded in-memory processing: the Phase 1 recommendation for analytics reads.
_MAX_POSTINGS = 20_000
_MAX_CATALOG_ENTRIES = 1000
_DEFAULT_SKILL_LIMIT = 10
_TOP_SKILLS_PER_ENTITY = 10  # per company / per job family
_MAX_COMPARISON_ENTITIES = 6  # bounds the comparison response size
# Real archives contain thousands of distinct employers. The dashboard and
# filter list are capped so the payload stays responsive, while the true count
# is still reported separately.
_MAX_RESPONSE_COMPANIES = 200
_MAX_FILTER_COMPANIES = 300
_MAX_FILTER_LOCATIONS = 200

# Calendar-year demand-share weights, newest first (see trend score above).
_TREND_WEIGHTS_BY_YEAR_OFFSET = (0.40, 0.30, 0.20, 0.10)

_FULL_WINDOW = (1, 12)

_MOCK_DISCLAIMER = (
    "Demo dataset: figures come from the PLACER fictional mock job-market data "
    "and are not verified real-world hiring statistics."
)

# Aggregate-level fields only — job descriptions and JD text are never read.
_POSTING_PROJECTION: dict[str, Any] = {
    "_id": 0,
    "company_name": 1,
    "company_slug": 1,
    "company_industry": 1,
    "job_family": 1,
    "technical_skills": 1,
    "soft_skills": 1,
    "location": 1,
    "source": 1,
    "dataset_version": 1,
    "imported_at": 1,
    "year": 1,
    "month": 1,
}


class MarketQueryError(ValueError):
    """Invalid market-analytics query values (company/location/year range)."""


@dataclass(frozen=True)
class MarketQuery:
    """Validated-shape query parameters for the market analytics endpoint.

    Enum-style values arrive as plain strings (the router unwraps them) so the
    service layer stays decoupled from request parsing.
    """

    year_from: int | None = None
    year_to: int | None = None
    company: str | None = None
    job_family: str | None = None
    location: str | None = None
    skill_category: str | None = None
    technical_only: bool = False
    # "mock" | "real" | "all" | an exact source id | None (server default).
    source: str | None = None
    sort: str = "trending"
    limit: int = _DEFAULT_SKILL_LIMIT


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable without a database)
# ---------------------------------------------------------------------------


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole > 0 else 0.0


def _growth_pct(current: int, previous: int) -> float | None:
    """YoY growth between two comparable counts; None when previous is zero."""
    if previous == 0:
        return None
    return round(100.0 * (current - previous) / previous, 1)


def _classify_trend(current: int, previous: int, comparable: bool) -> str | None:
    """Shared trend classification (see module docstring for thresholds)."""
    if not comparable:
        return None
    if previous == 0:
        return "emerging" if current > 0 else None
    growth = 100.0 * (current - previous) / previous
    if growth >= 10.0:
        return "rising"
    if growth <= -10.0:
        return "declining"
    return "stable"


def _slugify(name: str) -> str:
    """Fallback slug for a skill name missing from the catalog."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return slug or "skill"


def _period_info(year: int, window: tuple[int, int]) -> MarketPeriodInfo:
    start, end = window
    label = f"Full year {year}" if end == 12 else f"Jan-{calendar.month_abbr[end]} {year}"
    return MarketPeriodInfo(year=year, start_month=start, end_month=end, label=label)


def _comparison_end_month(coverage: dict[int, int], latest_year: int) -> int:
    """End month of the comparison window for ``latest_year``.

    Uses the highest month actually present in the latest year, capped by the
    previous year's coverage so both sides of a YoY comparison always span the
    same calendar months. Falls back to a full year when coverage is unknown.
    """
    latest = coverage.get(latest_year, 12)
    previous = coverage.get(latest_year - 1, 12)
    return max(1, min(12, latest, previous))


def _historical_end_month(coverage: dict[int, int], year: int) -> int:
    """End month for one historical year's own YoY comparison."""
    return _comparison_end_month(coverage, year)


def _window_count(full: Counter, windowed: Counter, year: int, use_window: bool) -> int:
    """A skill's posting count inside a year, restricted to the window."""
    return (windowed if use_window else full).get(year, 0)


def _trend_score(
    skill_yearly: Counter,
    yearly_totals: Counter,
    years: list[int],
    latest_year: int,
    *,
    skill_yearly_window: Counter | None = None,
    yearly_totals_window: Counter | None = None,
    use_partial_window: bool = False,
) -> float:
    """Weighted mean of year-wise demand shares (see module docstring).

    When the latest year is a partial window, EVERY compared year must use the
    same window. Mixing a partial latest year with full previous years would
    make the score drop for purely calendar reasons and produce a false
    "declining" signal.
    """
    if use_partial_window:
        skill_yearly = (
            skill_yearly_window if skill_yearly_window is not None else skill_yearly
        )
        yearly_totals = (
            yearly_totals_window if yearly_totals_window is not None else yearly_totals
        )
    weights: dict[int, float] = {}
    for year in years:
        offset = latest_year - year
        weights[year] = (
            _TREND_WEIGHTS_BY_YEAR_OFFSET[offset]
            if 0 <= offset < len(_TREND_WEIGHTS_BY_YEAR_OFFSET)
            else 0.0
        )
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        # Every present year is outside the 4-year weighting window — fall
        # back to equal weighting instead of producing a zero score.
        weights = {year: 1.0 for year in years}
        weight_sum = float(len(years))
    score = 0.0
    for year in years:
        share = _pct(skill_yearly.get(year, 0), yearly_totals.get(year, 0))
        score += (weights[year] / weight_sum) * share
    return round(score, 2)


class _SkillScope:
    """Decides which of a posting's skills fall inside the skill filters."""

    def __init__(self, catalog_by_name: dict[str, Any], query: MarketQuery):
        self._technical_only = query.technical_only
        self._allowed: set[str] | None = None
        if query.skill_category is not None:
            self._allowed = {
                name
                for name, doc in catalog_by_name.items()
                if doc.category.value == query.skill_category
            }

    def select(self, row: dict[str, Any]) -> list[str]:
        technical = row.get("technical_skills") or []
        soft = row.get("soft_skills") or []
        names = technical if self._technical_only else technical + soft
        if self._allowed is not None:
            names = [name for name in names if name in self._allowed]
        return names


def _identity_for(name: str, catalog_by_name: dict[str, Any]) -> tuple[str, str | None, bool]:
    """(slug, category, is_technical) for a skill name.

    Skills missing from the catalog (defensive: cannot happen with the Phase 2
    dataset) get a slugified fallback and are treated as technical.
    """
    doc = catalog_by_name.get(name)
    if doc is not None:
        return doc.slug, doc.category.value, doc.is_technical
    return _slugify(name), None, True


# ---------------------------------------------------------------------------
# In-memory aggregation over the filtered postings (single pass)
# ---------------------------------------------------------------------------


@dataclass
class _Aggregate:
    total_postings: int = 0
    years: list[int] = field(default_factory=list)
    yearly_totals: Counter = field(default_factory=Counter)
    yearly_window_totals: Counter = field(default_factory=Counter)
    skill_totals: Counter = field(default_factory=Counter)
    skill_yearly: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    skill_yearly_window: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    companies: dict[str, dict[str, Any]] = field(default_factory=dict)
    families: dict[str, dict[str, Any]] = field(default_factory=dict)
    coverage: dict[int, int] = field(default_factory=dict)
    latest_year: int | None = None
    current_window: tuple[int, int] = _FULL_WINDOW
    current_total: int = 0
    previous_total: int = 0
    comparable: bool = False


def _derive_coverage(rows: list[dict[str, Any]]) -> dict[int, int]:
    """Highest month present per year in ``rows`` (fallback when no map given)."""
    coverage: dict[int, int] = {}
    for row in rows:
        year = int(row["year"])
        month = int(row["month"])
        coverage[year] = max(coverage.get(year, 0), month)
    return coverage


def _aggregate_postings(
    rows: list[dict[str, Any]],
    catalog_by_name: dict[str, Any],
    query: MarketQuery,
    coverage: dict[int, int] | None = None,
) -> _Aggregate:
    """One in-memory pass over the filtered postings.

    ``coverage`` must be computed over the source population BEFORE the
    user's filters so the comparison window is stable; direct callers/tests
    may omit it, in which case coverage is derived from ``rows``.
    """
    agg = _Aggregate()
    scope = _SkillScope(catalog_by_name, query)
    agg.coverage = dict(coverage) if coverage is not None else _derive_coverage(rows)

    years_present = sorted({int(row["year"]) for row in rows})
    latest_year = years_present[-1] if years_present else None
    window_end = (
        _comparison_end_month(agg.coverage, latest_year)
        if latest_year is not None
        else _FULL_WINDOW[1]
    )

    for row in rows:
        year = int(row["year"])
        month = int(row["month"])
        in_window = month <= window_end

        agg.yearly_totals[year] += 1
        if in_window:
            agg.yearly_window_totals[year] += 1

        company = agg.companies.setdefault(
            row["company_slug"],
            {
                "name": row["company_name"],
                "industry": row["company_industry"],
                "count": 0,
                "yearly": Counter(),
                "skills": Counter(),
            },
        )
        company["count"] += 1
        company["yearly"][year] += 1

        family = agg.families.setdefault(
            row["job_family"],
            {"count": 0, "yearly": Counter(), "skills": Counter()},
        )
        family["count"] += 1
        family["yearly"][year] += 1

        # A skill is counted once per posting: the per-posting skill lists are
        # duplicate-free by model invariant, so list membership is distinct.
        for name in scope.select(row):
            agg.skill_totals[name] += 1
            agg.skill_yearly[name][year] += 1
            if in_window:
                agg.skill_yearly_window[name][year] += 1
            company["skills"][name] += 1
            family["skills"][name] += 1

    agg.total_postings = len(rows)
    agg.years = sorted(agg.yearly_totals)
    agg.latest_year = latest_year

    if agg.latest_year is not None:
        agg.current_window = (1, window_end)
        use_window = agg.current_window[1] != 12
        agg.current_total = _window_count(
            agg.yearly_totals, agg.yearly_window_totals, agg.latest_year, use_window
        )
        agg.previous_total = _window_count(
            agg.yearly_totals, agg.yearly_window_totals, agg.latest_year - 1, use_window
        )
        # Comparable only when the previous window actually has postings in
        # the filtered population — this is what stops a filter from turning
        # every skill into a fake "emerging" trend.
        agg.comparable = agg.previous_total > 0

    return agg


# ---------------------------------------------------------------------------
# Response assembly
# ---------------------------------------------------------------------------


def _skill_record(
    name: str,
    agg: _Aggregate,
    catalog_by_name: dict[str, Any],
) -> dict[str, Any]:
    slug, category, is_technical = _identity_for(name, catalog_by_name)
    full = agg.skill_yearly[name]
    windowed = agg.skill_yearly_window[name]
    use_window = agg.current_window[1] != 12
    latest_year = agg.latest_year or 0
    current = _window_count(full, windowed, latest_year, use_window)
    previous = _window_count(full, windowed, latest_year - 1, use_window)
    return {
        "name": name,
        "slug": slug,
        "category": category,
        "is_technical": is_technical,
        "posting_count": agg.skill_totals[name],
        "demand_pct": _pct(agg.skill_totals[name], agg.total_postings),
        "trend_score": _trend_score(
            full,
            agg.yearly_totals,
            agg.years,
            latest_year,
            skill_yearly_window=windowed,
            yearly_totals_window=agg.yearly_window_totals,
            use_partial_window=use_window,
        ),
        "trend": _classify_trend(current, previous, agg.comparable),
        "yoy_growth_pct": _growth_pct(current, previous),
        "current_period_count": current,
        "previous_period_count": previous,
        "yearly_counts": {year: full.get(year, 0) for year in agg.years},
        "yearly_demand_pct": {
            year: _pct(full.get(year, 0), agg.yearly_totals.get(year, 0))
            for year in agg.years
        },
        "_full": full,
        "_window": windowed,
    }


def _trending_skill_from_record(record: dict[str, Any]) -> TrendingSkill:
    """Convert an internal ``_skill_record`` dict into the shared model.

    Used by both the dashboard response and the comparison endpoint so the
    trend math is assembled in exactly one place.
    """
    return TrendingSkill(
        name=record["name"],
        slug=record["slug"],
        category=record["category"],
        is_technical=record["is_technical"],
        posting_count=record["posting_count"],
        demand_pct=record["demand_pct"],
        trend_score=record["trend_score"],
        trend=record["trend"],
        yoy_growth_pct=record["yoy_growth_pct"],
        current_period_count=record["current_period_count"],
        previous_period_count=record["previous_period_count"],
        yearly_counts=record["yearly_counts"],
        yearly_demand_pct=record["yearly_demand_pct"],
    )


def _disclaimer_for(sources: list[str]) -> str:
    """Disclaimer that matches the actual origin of the figures."""
    if not sources:
        return _MOCK_DISCLAIMER
    real = [source for source in sources if not source_definition(source).is_mock]
    if not real:
        return _MOCK_DISCLAIMER
    attribution = source_attribution(real)
    if len(real) == len(sources):
        return (
            "Real public data: figures are derived from imported public job "
            f"postings. {attribution} They describe this imported sample, not "
            "verified institutional placement outcomes."
        )
    return (
        "Mixed sources: figures combine the fictional PLACER demo dataset with "
        f"real imported public postings. {attribution} Treat every trend as "
        "indicative only."
    )


def _dataset_version_for(sources: list[str], versions: set[str]) -> str:
    if len(versions) == 1:
        return next(iter(versions))
    if versions:
        return "mixed"
    # No rows carry a version (e.g. an empty filtered population): fall back
    # to the contract constant rather than inventing a source-specific one.
    return MARKET_DATASET_VERSION


def _build_meta(
    agg: _Aggregate,
    sources: list[str],
    dataset_version: str,
    latest_import_at: datetime | None = None,
) -> MarketMeta:
    """Dataset identity + comparison-window metadata shared by every response."""
    ordered_sources = sorted({source for source in sources if source})
    is_mock_data = bool(ordered_sources) and all(
        source_definition(source).is_mock for source in ordered_sources
    )
    if not ordered_sources:
        is_mock_data = True
    has_mock = any(source_definition(source).is_mock for source in ordered_sources)
    data_origin = "mock" if is_mock_data else ("mixed" if has_mock else "real")
    if len(ordered_sources) == 1:
        source_value = ordered_sources[0]
    elif ordered_sources:
        source_value = "mixed"
    else:
        source_value = "mock"

    end_month = agg.current_window[1]
    comparison_period = (
        "Full year"
        if end_month == 12
        else f"Jan-{calendar.month_abbr[end_month]}"
    )

    return MarketMeta(
        source=source_value,
        dataset_version=dataset_version,
        is_mock_data=is_mock_data,
        comparison_period=comparison_period,
        is_partial_year=end_month != 12,
        disclaimer=_disclaimer_for(ordered_sources),
        current_period=(
            _period_info(agg.latest_year, agg.current_window)
            if agg.latest_year is not None
            else None
        ),
        previous_period=(
            _period_info(agg.latest_year - 1, agg.current_window)
            if agg.latest_year is not None
            else None
        ),
        comparison_comparable=agg.comparable,
        filtered_years=agg.years,
        sources=ordered_sources,
        data_origin=data_origin,
        latest_import_at=latest_import_at,
    )


def _top_skills(
    skill_counts: Counter,
    denominator: int,
    catalog_by_name: dict[str, Any],
) -> list[MarketSkillDemand]:
    ordered = sorted(skill_counts.items(), key=lambda item: (-item[1], item[0]))
    top = []
    for name, count in ordered[:_TOP_SKILLS_PER_ENTITY]:
        slug, category, _ = _identity_for(name, catalog_by_name)
        top.append(
            MarketSkillDemand(
                name=name,
                slug=slug,
                category=category,
                posting_count=count,
                demand_pct=_pct(count, denominator),
            )
        )
    return top


def _build_response(
    agg: _Aggregate,
    catalog_by_name: dict[str, Any],
    query: MarketQuery,
    sources: list[str],
    dataset_version: str,
    latest_import_at: datetime | None = None,
) -> MarketAnalyticsResponse:
    years = agg.years
    records = {
        name: _skill_record(name, agg, catalog_by_name) for name in agg.skill_totals
    }

    # --- Trending skills (sorted + limited) -------------------------------
    if query.sort == "demand":
        ordered = sorted(
            records.values(), key=lambda r: (-r["posting_count"], r["name"])
        )
    else:  # "trending" — highest weighted demand-share score first
        ordered = sorted(
            records.values(),
            key=lambda r: (-r["trend_score"], -r["posting_count"], r["name"]),
        )
    trending = [_trending_skill_from_record(r) for r in ordered[: query.limit]]

    # --- Historical trends (every in-scope skill, all filtered years) ------
    historical = []
    for r in sorted(records.values(), key=lambda r: (-r["posting_count"], r["name"])):
        year_items = []
        # One basis for the whole series: when the latest year is partial,
        # every year is restricted to the same Jan-<end> window. Mixing full
        # calendar years with a partial latest year (or plotting demand share
        # while growth uses counts) made declines look like rises.
        use_window = agg.current_window[1] != 12
        for year in years:
            partial = use_window or _historical_end_month(agg.coverage, year) < 12
            current = _window_count(r["_full"], r["_window"], year, partial)
            previous = _window_count(r["_full"], r["_window"], year - 1, partial)
            year_items.append(
                YearlySkillDemand(
                    year=year,
                    # Calendar-year totals stay available for callers that
                    # need them, but the comparable window is what the trend
                    # charts and growth figures use.
                    posting_count=r["yearly_counts"][year],
                    demand_pct=r["yearly_demand_pct"][year],
                    window_posting_count=current,
                    window_demand_pct=(
                        _pct(current, agg.yearly_window_totals.get(year, 0))
                        if partial
                        else r["yearly_demand_pct"][year]
                    ),
                    yoy_growth_pct=_growth_pct(current, previous),
                )
            )
        historical.append(
            HistoricalSkillTrend(
                name=r["name"], slug=r["slug"], category=r["category"], years=year_items
            )
        )

    # --- Emerging skills ---------------------------------------------------
    emerging = [
        EmergingSkill(
            name=r["name"],
            slug=r["slug"],
            category=r["category"],
            current_period_count=r["current_period_count"],
            current_period_demand_pct=_pct(
                r["current_period_count"], agg.current_total
            ),
            previous_period_count=r["previous_period_count"],
            trend="emerging",
        )
        for r in sorted(
            records.values(), key=lambda r: (-r["current_period_count"], r["name"])
        )
        if r["trend"] == "emerging"
    ]

    # --- Summary -----------------------------------------------------------
    most_demanded = None
    if records:
        best = min(records.values(), key=lambda r: (-r["posting_count"], r["name"]))
        most_demanded = MarketSkillDemand(
            name=best["name"],
            slug=best["slug"],
            category=best["category"],
            posting_count=best["posting_count"],
            demand_pct=best["demand_pct"],
        )
    summary = MarketSummary(
        total_postings=agg.total_postings,
        company_count=len(agg.companies),
        distinct_skill_count=len(records),
        most_demanded_skill=most_demanded,
        yoy_posting_growth_pct=_growth_pct(agg.current_total, agg.previous_total),
    )

    # --- Company analytics -------------------------------------------------
    # The response is capped, but ``summary.company_count`` above still reports
    # the true number of distinct employers in the filtered population.
    company_items = []
    for slug in sorted(agg.companies, key=lambda s: (-agg.companies[s]["count"], s)):
        if len(company_items) >= _MAX_RESPONSE_COMPANIES:
            break
        company = agg.companies[slug]
        company_items.append(
            CompanyMarketAnalytics(
                company_name=company["name"],
                company_slug=slug,
                industry=company["industry"],
                posting_count=company["count"],
                posting_share_pct=_pct(company["count"], agg.total_postings),
                top_skills=_top_skills(
                    company["skills"], company["count"], catalog_by_name
                ),
                yearly_counts={
                    year: company["yearly"].get(year, 0) for year in years
                },
            )
        )

    # --- Job-family analytics ---------------------------------------------
    family_items = []
    for family_name in sorted(agg.families, key=lambda f: (-agg.families[f]["count"], f)):
        family = agg.families[family_name]
        family_items.append(
            JobFamilyMarketAnalytics(
                job_family=family_name,
                posting_count=family["count"],
                posting_share_pct=_pct(family["count"], agg.total_postings),
                top_skills=_top_skills(
                    family["skills"], family["count"], catalog_by_name
                ),
                yearly_counts={year: family["yearly"].get(year, 0) for year in years},
            )
        )

    meta = _build_meta(agg, sources, dataset_version, latest_import_at)

    return MarketAnalyticsResponse(
        meta=meta,
        summary=summary,
        trending_skills=trending,
        historical_trends=historical,
        emerging_skills=emerging,
        companies=company_items,
        job_families=family_items,
    )


# ---------------------------------------------------------------------------
# Service (Router -> Service -> Repository)
# ---------------------------------------------------------------------------


class MarketAnalyticsService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.postings = JobMarketPostingRepository(db)
        self.catalog = MarketSkillCatalogRepository(db)

    # -- Source selection ---------------------------------------------------

    async def resolve_source_filter(self, source: str | None) -> dict[str, Any]:
        """Mongo filter selecting the requested source group.

        ``None`` means "server default": the demo dataset when it exists (so
        the historical demo series is unchanged), otherwise all real rows.
        ``"real"`` selects every non-mock source, ``"all"`` selects everything,
        and any other value is treated as an exact source id. Source ids are
        stored lower-case, so the value is normalised before matching.
        """
        normalized = (source or "").strip().casefold()
        if normalized in ("", "default"):
            has_mock = await self.postings.count({"source": "mock"}) > 0
            normalized = "mock" if has_mock else "real"
        if normalized == "all":
            return {}
        if normalized == "real":
            return {"source": {"$ne": "mock"}}
        return {"source": normalized}

    async def coverage_for(self, source: str | None) -> dict[int, int]:
        """Month coverage of the source population, before user filters.

        The comparison window must not shrink when a user narrows a year or
        company filter, so this is always computed over the whole selected
        source group.
        """
        source_filter = await self.resolve_source_filter(source)
        return await self.postings.month_coverage(source_filter)

    async def get_source_info(self) -> list[MarketSourceInfo]:
        """Per-source provenance for the filter panel / metadata banner."""
        infos: list[MarketSourceInfo] = []
        for row in await self.postings.source_stats():
            source_id = row.get("_id")
            if not isinstance(source_id, str) or not source_id:
                continue
            definition = source_definition(source_id)
            infos.append(
                MarketSourceInfo(
                    id=source_id,
                    label=definition.label,
                    is_mock=definition.is_mock,
                    posting_count=int(row.get("posting_count") or 0),
                    latest_posted_at=row.get("latest_posted_at"),
                    imported_at=row.get("imported_at"),
                    license=definition.license,
                    homepage=definition.homepage,
                )
            )
        infos.sort(key=lambda info: (not info.is_mock, info.label))
        return infos

    # -- Public API ---------------------------------------------------------

    async def build_posting_query(
        self,
        year_from: int | None,
        year_to: int | None,
        company: str | None,
        job_family: str | None,
        location: str | None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Validated Mongo posting query for the given POSTING filters.

        Public facade for the Phase 8 skill-gap service, which must apply the
        EXACT same posting-population filter semantics (and the same
        unknown-company/location -> 400 validation) as the market dashboard
        without duplicating the resolution logic. Skill-scope filters are not
        part of the posting population — callers apply them via
        ``_aggregate_postings``'s ``MarketQuery``.
        """
        self._validate_year_range_values(year_from, year_to)
        mongo_query: dict[str, Any] = await self.resolve_source_filter(source)
        year_filter = self._year_filter(year_from, year_to)
        if year_filter:
            mongo_query["year"] = year_filter
        if job_family is not None:
            mongo_query["job_family"] = job_family
        if company is not None:
            mongo_query["company_slug"] = await self._resolve_company(company)
        if location is not None:
            mongo_query["location"] = await self._resolve_location(location)
        return mongo_query

    async def get_available_filters(
        self, source: str | None = None
    ) -> MarketFiltersResponse:
        """Filter options derived live from the selected source group.

        Nothing is hardcoded: years, companies, job families, locations and
        skill categories all come from the stored postings/catalog. The
        ``sources`` list always describes every source present in the
        collection so the UI can offer an honest switch.
        """
        source_filter = await self.resolve_source_filter(source)
        years = sorted(
            int(year)
            for year in await self.postings.distinct_values("year", source_filter)
        )
        job_families = sorted(
            str(family)
            for family in await self.postings.distinct_values(
                "job_family", source_filter
            )
        )
        location_rows, location_total = await self.postings.location_counts(
            source_filter, limit=_MAX_FILTER_LOCATIONS
        )
        locations = [
            str(row["_id"])
            for row in location_rows
            if row.get("_id")
        ]
        # Selection is by posting volume (the cap keeps the most common
        # locations), but the list itself stays alphabetical for the UI.
        locations.sort()

        company_rows, company_total = await self.postings.company_counts(
            source_filter, limit=_MAX_FILTER_COMPANIES
        )
        companies = [
            CompanyFilterOption(slug=row["_id"], name=row["name"])
            for row in company_rows
            if row.get("_id") and row.get("name")
        ]

        catalog_docs = await self.catalog.find_many(limit=_MAX_CATALOG_ENTRIES)
        categories = sorted({doc.category.value for doc in catalog_docs})

        return MarketFiltersResponse(
            years=years,
            companies=companies,
            company_total=company_total,
            job_families=job_families,
            locations=locations,
            location_total=location_total,
            skill_categories=categories,
            sources=await self.get_source_info(),
        )

    async def source_metadata(
        self, rows: list[dict[str, Any]], source: str | None
    ) -> tuple[list[str], str, datetime | None]:
        """(sources, dataset_version, latest_import_at) for a response.

        The exact source ids are read from the analysed rows, so a mixed view
        reports every source that actually contributed. When the filtered
        population is empty the selected source group is reported instead of
        silently claiming the demo dataset.
        """
        if rows:
            sources = sorted({str(row.get("source") or "mock") for row in rows})
            versions = {
                str(row.get("dataset_version") or MARKET_DATASET_VERSION)
                for row in rows
            }
            latest_import = max(
                (row["imported_at"] for row in rows if row.get("imported_at")),
                default=None,
            )
            return sources, _dataset_version_for(sources, versions), latest_import

        source_filter = await self.resolve_source_filter(source)
        versions = {
            str(version)
            for version in await self.postings.distinct_values(
                "dataset_version", source_filter
            )
            if version
        }
        normalized = (source or "").strip().casefold()
        info = await self.get_source_info()
        if normalized in ("", "default"):
            sources = [i.id for i in info if i.is_mock] or [
                i.id for i in info if not i.is_mock
            ]
        elif normalized == "all":
            sources = [i.id for i in info]
        elif normalized == "real":
            sources = [i.id for i in info if not i.is_mock]
        else:
            sources = [normalized]
        return sources, _dataset_version_for(sources, versions), None

    async def get_market_analytics(self, query: MarketQuery) -> MarketAnalyticsResponse:
        self._validate_year_range(query)
        source_filter = await self.resolve_source_filter(query.source)
        mongo_query = await self._build_mongo_query(query, source_filter)
        coverage = await self.postings.month_coverage(source_filter)

        rows = await self.postings.find_projected(
            mongo_query, _POSTING_PROJECTION, limit=_MAX_POSTINGS
        )
        catalog_docs = await self.catalog.find_many(limit=_MAX_CATALOG_ENTRIES)
        catalog_by_name = {doc.name: doc for doc in catalog_docs}

        agg = _aggregate_postings(rows, catalog_by_name, query, coverage)
        sources, dataset_version, latest_import_at = await self.source_metadata(
            rows, query.source
        )

        logger.debug(
            "Market analytics: %d posting(s) from %s analysed for filters %s",
            agg.total_postings,
            sources,
            mongo_query,
        )
        return _build_response(
            agg,
            catalog_by_name,
            query,
            sources,
            dataset_version,
            latest_import_at,
        )

    async def get_market_comparison(
        self,
        dimension: str,
        entity_values: list[str],
        year_from: int | None,
        year_to: int | None,
        cross_company: str | None,
        cross_job_family: str | None,
        location: str | None,
        source: str | None = None,
    ) -> MarketComparisonResponse:
        """Phase 5 entity comparison (companies or job families).

        The dimension's own filter is replaced by the entity selection; the
        other posting filters still apply. See the module docstring for the
        exact semantics.
        """
        self._validate_year_range_values(year_from, year_to)
        if not entity_values:
            raise MarketQueryError("Select at least one entity to compare.")

        source_filter = await self.resolve_source_filter(source)
        coverage = await self.postings.month_coverage(source_filter)
        mongo_query: dict[str, Any] = dict(source_filter)
        year_filter = self._year_filter(year_from, year_to)
        if year_filter:
            mongo_query["year"] = year_filter
        if location is not None:
            mongo_query["location"] = await self._resolve_location(location)

        if dimension == "company":
            if cross_job_family is not None:
                mongo_query["job_family"] = cross_job_family
            info = await self._company_directory()
            selected = self._select_company_entities(entity_values, info)
        elif dimension == "job_family":
            if cross_company is not None:
                mongo_query["company_slug"] = await self._resolve_company(cross_company)
            known_families = {
                str(family).casefold(): str(family)
                for family in await self.postings.distinct_values("job_family")
            }
            selected = self._select_family_entities(entity_values, known_families)
        else:
            raise MarketQueryError(f"Unknown comparison dimension '{dimension}'.")

        if len(selected) > _MAX_COMPARISON_ENTITIES:
            raise MarketQueryError(
                f"At most {_MAX_COMPARISON_ENTITIES} entities can be compared "
                f"at once (got {len(selected)})."
            )

        rows = await self.postings.find_projected(
            mongo_query, _POSTING_PROJECTION, limit=_MAX_POSTINGS
        )
        catalog_docs = await self.catalog.find_many(limit=_MAX_CATALOG_ENTRIES)
        catalog_by_name = {doc.name: doc for doc in catalog_docs}

        # The unfiltered-by-dimension population anchors the comparison
        # window and the posting-share denominator.
        overall = _aggregate_postings(rows, catalog_by_name, MarketQuery(), coverage)
        sources, dataset_version, latest_import_at = await self.source_metadata(
            rows, source
        )
        meta = _build_meta(overall, sources, dataset_version, latest_import_at)

        entities: list[ComparisonEntityAnalytics] = []
        for key in selected:
            if dimension == "company":
                subset = [row for row in rows if row["company_slug"] == key]
                label = info[key]["name"]
                industry: str | None = info[key]["industry"]
            else:
                subset = [row for row in rows if row["job_family"] == key]
                label = key
                industry = None

            entity_agg = _aggregate_postings(
                subset, catalog_by_name, MarketQuery(), coverage
            )
            # Align the window/comparability with the overall population so a
            # company that stopped posting in 2024 is not silently compared
            # full-year 2024 vs 2023 while the rest of the dashboard compares
            # partial-year windows.
            entity_agg.comparable = False
            if overall.latest_year is not None:
                entity_agg.latest_year = overall.latest_year
                entity_agg.current_window = overall.current_window
                partial = overall.current_window[1] != 12
                entity_agg.current_total = _window_count(
                    entity_agg.yearly_totals,
                    entity_agg.yearly_window_totals,
                    overall.latest_year,
                    partial,
                )
                entity_agg.previous_total = _window_count(
                    entity_agg.yearly_totals,
                    entity_agg.yearly_window_totals,
                    overall.latest_year - 1,
                    partial,
                )
                entity_agg.comparable = entity_agg.previous_total > 0

            records = [
                _skill_record(name, entity_agg, catalog_by_name)
                for name in sorted(entity_agg.skill_totals)
            ]
            records.sort(key=lambda r: (-r["posting_count"], r["name"]))
            skills = [_trending_skill_from_record(r) for r in records]
            tech_instances = sum(
                skill.posting_count for skill in skills if skill.is_technical
            )
            soft_instances = sum(
                skill.posting_count for skill in skills if not skill.is_technical
            )
            entity_total = tech_instances + soft_instances
            entities.append(
                ComparisonEntityAnalytics(
                    entity_key=key,
                    entity_label=label,
                    industry=industry,
                    posting_count=entity_agg.total_postings,
                    posting_share_pct=_pct(
                        entity_agg.total_postings, overall.total_postings
                    ),
                    tech_skill_instances=tech_instances,
                    soft_skill_instances=soft_instances,
                    tech_share_pct=_pct(tech_instances, entity_total),
                    soft_share_pct=_pct(soft_instances, entity_total),
                    yearly_counts={
                        year: entity_agg.yearly_totals.get(year, 0)
                        for year in overall.years
                    },
                    skills=skills,
                )
            )

        logger.debug(
            "Market comparison: dimension=%s entities=%s postings=%d",
            dimension,
            selected,
            overall.total_postings,
        )
        return MarketComparisonResponse(
            meta=meta, dimension=dimension, entities=entities
        )

    # -- Comparison resolution helpers --------------------------------------

    async def _company_directory(self) -> dict[str, dict[str, str]]:
        """All known companies: slug -> {name, industry} (unfiltered)."""
        rows = await self.postings.find_projected(
            {},
            {"_id": 0, "company_slug": 1, "company_name": 1, "company_industry": 1},
            limit=_MAX_POSTINGS,
        )
        directory: dict[str, dict[str, str]] = {}
        for row in rows:
            directory.setdefault(
                row["company_slug"],
                {"name": row["company_name"], "industry": row["company_industry"]},
            )
        return directory

    @staticmethod
    def _select_company_entities(
        values: list[str], directory: dict[str, dict[str, str]]
    ) -> list[str]:
        """Resolve company slugs/names to canonical slugs, deduped, in order."""
        by_slug: dict[str, str] = {}
        by_name: dict[str, str] = {}
        for slug, entry in directory.items():
            by_slug.setdefault(slug.casefold(), slug)
            by_name.setdefault(entry["name"].casefold(), slug)

        selected: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = value.strip().casefold()
            slug = by_slug.get(key) or by_name.get(key)
            if slug is None:
                raise MarketQueryError(
                    f"Unknown company '{value}'. Use a company slug or name "
                    "listed by GET /api/v1/analytics/tpo/market/filters."
                )
            if slug not in seen:
                seen.add(slug)
                selected.append(slug)
        return selected

    @staticmethod
    def _select_family_entities(
        values: list[str], known_families: dict[str, str]
    ) -> list[str]:
        """Resolve job-family names (case-insensitive), deduped, in order."""
        selected: list[str] = []
        seen: set[str] = set()
        for value in values:
            family = known_families.get(value.strip().casefold())
            if family is None:
                raise MarketQueryError(
                    f"Unknown job family '{value}'. Use a job family listed "
                    "by GET /api/v1/analytics/tpo/market/filters."
                )
            if family not in seen:
                seen.add(family)
                selected.append(family)
        return selected

    # -- Validation ---------------------------------------------------------

    @staticmethod
    def _validate_year_range_values(year_from: int | None, year_to: int | None) -> None:
        if (
            year_from is not None
            and year_to is not None
            and year_from > year_to
        ):
            raise MarketQueryError(
                f"year_from ({year_from}) cannot be after year_to ({year_to})."
            )

    @classmethod
    def _validate_year_range(cls, query: MarketQuery) -> None:
        cls._validate_year_range_values(query.year_from, query.year_to)

    @staticmethod
    def _year_filter(year_from: int | None, year_to: int | None) -> dict[str, int]:
        year_filter: dict[str, int] = {}
        if year_from is not None:
            year_filter["$gte"] = year_from
        if year_to is not None:
            year_filter["$lte"] = year_to
        return year_filter

    async def _build_mongo_query(
        self, query: MarketQuery, source_filter: dict[str, Any]
    ) -> dict[str, Any]:
        mongo_query: dict[str, Any] = dict(source_filter)
        year_filter = self._year_filter(query.year_from, query.year_to)
        if year_filter:
            mongo_query["year"] = year_filter
        if query.job_family is not None:
            mongo_query["job_family"] = query.job_family
        if query.company is not None:
            mongo_query["company_slug"] = await self._resolve_company(query.company)
        if query.location is not None:
            mongo_query["location"] = await self._resolve_location(query.location)
        return mongo_query

    async def _resolve_company(self, value: str) -> str:
        """Resolve a company slug or name to the canonical company_slug."""
        rows = await self.postings.find_projected(
            {}, {"_id": 0, "company_slug": 1, "company_name": 1}, limit=_MAX_POSTINGS
        )
        by_slug: dict[str, str] = {}
        by_name: dict[str, str] = {}
        for row in rows:
            by_slug.setdefault(row["company_slug"].casefold(), row["company_slug"])
            by_name.setdefault(row["company_name"].casefold(), row["company_slug"])
        key = value.strip().casefold()
        if key in by_slug:
            return by_slug[key]
        if key in by_name:
            return by_name[key]
        raise MarketQueryError(
            f"Unknown company '{value}'. Use a company slug or name listed by "
            "GET /api/v1/analytics/tpo/market/filters."
        )

    async def _resolve_location(self, value: str) -> str:
        known = {
            str(location).casefold(): str(location)
            for location in await self.postings.distinct_values("location")
        }
        key = value.strip().casefold()
        if key in known:
            return known[key]
        raise MarketQueryError(
            f"Unknown location '{value}'. Use a location listed by "
            "GET /api/v1/analytics/tpo/market/filters."
        )
