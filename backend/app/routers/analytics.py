from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Literal

from app.core.database import get_database
from app.core.deps import CurrentUser, require_role
from app.models.analytics import (
    AdminActivityResponse,
    AdminAnalyticsResponse,
    AdminApplicationFiltersResponse,
    AdminApplicationRecordsResponse,
    DriveApplicantsResponse,
    DriveAssessmentRanking,
    DriveParticipantsResponse,
    SkillGapAnalysisResponse,
    SkillGapSort,
    SkillGapStudentFilter,
    SkillGapStudentsResponse,
    StudentAnalyticsResponse,
    TpoAnalyticsResponse,
    TpoApplicationAnalyticsResponse,
    TpoApplicationRecordsResponse,
)
from app.models.market import JobFamily, MarketFiltersResponse, SkillCategory
from app.services.analytics_service import AnalyticsError, AnalyticsService
from app.services.market_analytics_service import (
    MarketAnalyticsService,
    MarketQueryError,
)
from app.services.skill_gap_service import SkillGapError, SkillGapService

router = APIRouter()


@router.get("/tpo", response_model=TpoAnalyticsResponse)
async def get_tpo_analytics(
    current_user: CurrentUser = Depends(require_role("tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = AnalyticsService(db)
    return await service.get_tpo_analytics(current_user.id)


@router.get("/student/me", response_model=StudentAnalyticsResponse)
async def get_student_analytics(
    current_user: CurrentUser = Depends(require_role("student")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """The authenticated student's own dashboard analytics.

    Only this student's applications and submitted attempts are read; there
    is no student id parameter, so one student can never request another's
    data.
    """
    service = AnalyticsService(db)
    try:
        return await service.get_student_analytics(current_user.id)
    except AnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/tpo/applications", response_model=TpoApplicationAnalyticsResponse)
async def get_tpo_application_analytics(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    top_n: int = Query(default=8, ge=1, le=50),
    company_sort: Literal["applications", "shortlisted", "name"] = Query(
        default="applications"
    ),
    current_user: CurrentUser = Depends(require_role("tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Application analytics across the authenticated TPO's OWN drives.

    ``date_from``/``date_to`` filter by application ``applied_at`` (inclusive
    whole days). Department grouping, the zero-filled monthly trend and the
    sorted Top-N company breakdown all use that same filtered population.
    """
    service = AnalyticsService(db)
    try:
        return await service.get_tpo_application_analytics(
            current_user.id,
            date_from=date_from,
            date_to=date_to,
            top_n=top_n,
            company_sort=company_sort,
        )
    except AnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/tpo/applications/records", response_model=TpoApplicationRecordsResponse)
async def get_tpo_application_records(
    status: Literal["applied", "shortlisted", "rejected"] | None = Query(
        default=None
    ),
    company_id: str | None = Query(default=None, max_length=64),
    department: str | None = Query(default=None, max_length=120),
    drive_id: str | None = Query(default=None, max_length=64),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_role("tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Application rows behind the authenticated TPO's OWN analytics charts.

    Each chart interaction (a status slice, a company bar, a department bar,
    a drive bar) passes its own filter here, so the drill-down lists exactly
    the applications that produced the clicked number. Ownership is enforced
    server-side; only identity + outcome fields are returned.
    """
    service = AnalyticsService(db)
    try:
        return await service.get_tpo_application_records(
            current_user.id,
            status=status,
            company_id=company_id,
            department=department,
            drive_id=drive_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            limit=limit,
        )
    except AnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/tpo/drives/{drive_id}/ranking", response_model=DriveAssessmentRanking)
async def get_drive_ranking(
    drive_id: str,
    current_user: CurrentUser = Depends(require_role("tpo", "admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Ranking for ONE drive's required assessment — shown inside that
    drive's expanded analytics breakdown (the standalone rankings section
    was relocated here). Admins may read any drive's ranking."""
    service = AnalyticsService(db)
    try:
        return await service.get_drive_ranking(
            current_user.id, drive_id, actor_role=current_user.role
        )
    except AnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/tpo/drives/{drive_id}/applicants", response_model=DriveApplicantsResponse)
async def get_drive_applicants(
    drive_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    current_user: CurrentUser = Depends(require_role("tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Students who applied to ONE drive (all application statuses)."""
    service = AnalyticsService(db)
    try:
        return await service.get_drive_applicants(current_user.id, drive_id, page, limit, search)
    except AnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/tpo/drives/{drive_id}/participants", response_model=DriveParticipantsResponse)
async def get_drive_participants(
    drive_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    current_user: CurrentUser = Depends(require_role("tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Students who actually started ONE drive's required assessment — one
    row per student, never per attempt."""
    service = AnalyticsService(db)
    try:
        return await service.get_drive_participants(current_user.id, drive_id, page, limit, search)
    except AnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ---------------------------------------------------------------------------
# Phase 8 — Skill Gap Analysis (TPO-only)
# ---------------------------------------------------------------------------


@router.get("/tpo/skill-gaps", response_model=SkillGapAnalysisResponse)
async def get_skill_gaps(
    current_user: CurrentUser = Depends(require_role("tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
    year_from: int | None = Query(default=None, ge=2000, le=2100),
    year_to: int | None = Query(default=None, ge=2000, le=2100),
    company: str | None = Query(default=None, max_length=200),
    job_family: JobFamily | None = Query(default=None),
    location: str | None = Query(default=None, max_length=100),
    skill_category: SkillCategory | None = Query(default=None),
    technical_only: bool = Query(default=False),
    sort: SkillGapSort = Query(default="priority"),
    source: str | None = Query(
        default=None,
        max_length=50,
        description=(
            "Market-data source group: 'mock', 'real', 'all', or one exact "
            "source id. Omit for the server default."
        ),
    ),
):
    """Skill gap analysis: industry demand (Market Insights dataset, same
    filter semantics as the market dashboard) vs. student evidence
    (assessment-demonstrated + self-reported, kept strictly separate)."""
    service = SkillGapService(db)
    try:
        return await service.get_skill_gaps(
            year_from=year_from,
            year_to=year_to,
            company=company,
            job_family=job_family.value if job_family is not None else None,
            location=location,
            skill_category=skill_category.value if skill_category is not None else None,
            technical_only=technical_only,
            sort=sort,
            source=source,
        )
    except MarketQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tpo/skill-gaps/filters", response_model=MarketFiltersResponse)
async def get_skill_gap_filters(
    current_user: CurrentUser = Depends(require_role("tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
    source: str | None = Query(
        default=None,
        max_length=50,
        description=(
            "Source group whose years/companies/locations are listed. Omit for "
            "the server default. The response always lists every source."
        ),
    ),
):
    """Filter options for the skill gap dashboard — the SAME live options the
    Market Insights filters endpoint derives (one dataset, one source)."""
    return await MarketAnalyticsService(db).get_available_filters(source)


@router.get(
    "/tpo/skill-gaps/{skill_id}/students", response_model=SkillGapStudentsResponse
)
async def get_skill_gap_students(
    skill_id: str,
    current_user: CurrentUser = Depends(require_role("tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    classification: SkillGapStudentFilter = Query(default="all"),
):
    """Students and their evidence for ONE demanded skill — the whole student
    population with a per-student classification (filterable), covering the
    no-evidence training audience too. Only fields relevant to THIS skill are
    returned; never unrelated assessment data or contact information."""
    service = SkillGapService(db)
    try:
        return await service.get_skill_students(
            skill_id, page, limit, search, classification
        )
    except SkillGapError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except MarketQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/activity", response_model=AdminActivityResponse)
async def get_admin_activity(
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """System-wide user distribution, department counts and monthly activity.

    Derived from real domain timestamps, never from the incomplete
    ``activity_logs`` collection.
    """
    service = AnalyticsService(db)
    return await service.get_admin_activity()


@router.get("/admin", response_model=AdminAnalyticsResponse)
async def get_admin_analytics(
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = AnalyticsService(db)
    return await service.get_admin_analytics()


@router.get("/admin/applications", response_model=AdminApplicationRecordsResponse)
async def get_admin_applications(
    status: Literal["applied", "shortlisted", "rejected"] | None = Query(default=None),
    company_id: str | None = Query(default=None, max_length=64),
    drive_id: str | None = Query(default=None, max_length=64),
    department: str | None = Query(default=None, max_length=120),
    assessment_completion: Literal["all", "completed", "pending", "not_required"] = Query(
        default="all"
    ),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Cross-drive application workspace for admins.

    The summary cards are computed before the status filter, so all four
    remain visible while a status filter is active. Status changes use the
    existing audited ``PATCH /drives/{drive_id}/applications/{application_id}``
    endpoint, which already authorises admins.
    """
    service = AnalyticsService(db)
    try:
        return await service.get_admin_applications(
            status=status,
            company_id=company_id,
            drive_id=drive_id,
            department=department,
            assessment_completion=None if assessment_completion == "all" else assessment_completion,
            date_from=date_from,
            date_to=date_to,
            page=page,
            limit=limit,
        )
    except AnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get(
    "/admin/applications/filters", response_model=AdminApplicationFiltersResponse
)
async def get_admin_application_filters(
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Live company / drive / department options for the admin workspace."""
    service = AnalyticsService(db)
    return await service.get_admin_application_filters()
