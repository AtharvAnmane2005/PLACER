"""
Response schemas for Phase 15 analytics.

Deliberately Python-side aggregation (fetch-then-group-in-memory) rather
than MongoDB aggregation pipelines — consistent with this project's
existing "simple first, optimize when there's a real need" approach (see
e.g. knowledge tracing being an EMA rather than real BKT), and it keeps
these endpoints testable against the same mongomock setup every other
test in this suite already uses without worrying about pipeline-operator
support gaps.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.market import MarketMeta


class ApplicationStatusBreakdown(BaseModel):
    """Full status split, including legacy ``selected`` outcomes.

    Kept for the admin overview, where a real ``selected`` record is a
    placement outcome. TPO dashboards deliberately use
    :class:`TpoApplicationStatusBreakdown` instead: their live pipeline is
    Applied -> Shortlisted / Rejected only.
    """

    applied: int
    shortlisted: int
    rejected: int
    selected: int


class TpoApplicationStatusBreakdown(BaseModel):
    """The three statuses a TPO actually manages.

    ``selected`` is intentionally absent: the current TPO workflow ends at
    shortlist/reject, so the dashboard never renders a Selected stage, filter
    or rate. Legacy ``selected`` records still exist in storage and remain
    visible in the admin overview; they are simply not part of this pipeline.
    """

    applied: int
    shortlisted: int
    rejected: int


class DriveAssessmentRankingEntry(BaseModel):
    """One student's standing in a drive assessment ranking.

    Only drive-type assessments (those linked to a drive) are ranked — practice
    assessment attempts are deliberately excluded from these leaderboards.
    """

    rank: int
    student_id: str
    student_name: str
    department: str | None = None
    cgpa: float | None = None
    score_pct: float
    submitted_at: datetime
    # Provenance — lets the UI mark demo rows instead of passing them off as
    # institutional results.
    is_synthetic: bool = False


class DriveAssessmentRanking(BaseModel):
    """Per-drive ranking — served by the drive-scoped ranking endpoint (the
    standalone rankings list was relocated into each drive's breakdown)."""

    drive_id: str
    job_title: str
    company_name: str
    assessment_id: str
    assessment_title: str
    entries: list[DriveAssessmentRankingEntry]


class DriveFunnel(BaseModel):
    drive_id: str
    job_title: str
    company_name: str
    status: str
    total_applications: int
    breakdown: TpoApplicationStatusBreakdown
    # Assessment linkage + participation (Phase: per-drive rankings). Additive
    # fields — the ranking detail itself moved to the per-drive endpoint.
    required_assessment_id: str | None = None
    assessment_title: str | None = None
    participant_count: int = 0  # unique students who STARTED the drive assessment
    submitted_participant_count: int = 0  # unique students with a SUBMITTED attempt
    # Eligible applications (eligibility_passed is not False — the same
    # convention as the screening summary). One application per student per
    # drive, so this is also the eligible-student denominator.
    eligible_application_count: int = 0
    # Completion = submitted participants / eligible applications, zero-safe.
    completion_rate_pct: float = 0.0


class TpoAnalyticsResponse(BaseModel):
    total_drives: int
    open_drives: int
    closed_drives: int
    total_applications: int
    breakdown: TpoApplicationStatusBreakdown
    drives: list[DriveFunnel]
    # Number of applications in this view that are flagged synthetic. The
    # dashboard renders a demo-data banner whenever this is nonzero.
    synthetic_application_count: int = 0


class DriveApplicantEntry(BaseModel):
    """One application behind a drive's applicant list.

    Every application status is included — the TPO sees the full funnel, not
    just active candidates. ``student_id`` is the student PROFILE id (the
    applications collection's ``student_id``), not the auth user id.
    """

    application_id: str
    student_id: str
    student_name: str
    department: str | None = None
    batch_year: int | None = None
    status: str
    applied_at: datetime
    is_synthetic: bool = False


class DriveApplicantsResponse(BaseModel):
    drive_id: str
    job_title: str
    company_name: str
    total: int
    page: int
    limit: int
    entries: list[DriveApplicantEntry]


class DriveParticipantEntry(BaseModel):
    """One student's participation in a drive's required assessment.

    One row per student (never per attempt): the displayed attempt is the
    student's best SUBMITTED attempt (same selection the ranking uses), or
    their latest in-progress attempt when they have not submitted yet — an
    in-progress attempt is a real attempt (the student actually started),
    while merely being assigned an assessment is not. ``score_pct`` is None
    for an in-progress attempt.
    """

    student_id: str
    student_name: str
    department: str | None = None
    batch_year: int | None = None
    attempt_id: str
    attempt_status: str  # "in_progress" | "submitted"
    score_pct: float | None = None
    started_at: datetime
    submitted_at: datetime | None = None
    is_synthetic: bool = False


class DriveParticipantsResponse(BaseModel):
    drive_id: str
    job_title: str
    company_name: str
    assessment_id: str | None = None
    assessment_title: str | None = None
    total: int  # unique participants across all pages
    page: int
    limit: int
    entries: list[DriveParticipantEntry]


class SkillMasteryOverview(BaseModel):
    skill_tag: str
    avg_mastery_pct: float
    student_count: int


class AdminUserRoleCount(BaseModel):
    """One user-account role and how many accounts hold it.

    Counted from the auth ``users`` collection (not the per-role profile
    collections), so every account is represented exactly once even if its
    profile document is missing.
    """

    role: Literal["student", "tpo", "admin"]
    count: int


class AdminDepartmentStudentCount(BaseModel):
    department: str  # free-text student department, or "Not specified"
    count: int


class AdminActivityMonthPoint(BaseModel):
    """One calendar month of platform activity.

    Counts come from domain timestamps (``users.created_at``,
    ``placement_drives.created_at`` and ``applications.applied_at``), never
    from the incomplete ``activity_logs`` collection.
    """

    month: str  # "YYYY-MM"
    new_students: int
    new_drives: int
    applications: int


class AdminAnalyticsResponse(BaseModel):
    total_students: int
    total_tpos: int
    total_drives: int
    open_drives: int
    closed_drives: int
    total_applications: int
    # Distinct students across all applications (never application rows).
    # ``students_with_applications`` is the user-facing name; the legacy
    # ``unique_applicants`` field is kept for older clients.
    unique_applicants: int = 0
    students_with_applications: int = 0
    total_companies: int = 0
    application_breakdown: ApplicationStatusBreakdown
    # Legacy "selected" rows are read-time mapped into ``shortlisted`` so the
    # three current statuses always sum to total_applications. This audit count
    # records how many legacy rows were mapped; the UI does not render it.
    legacy_selected: int = 0
    placed_students: int  # unique students with at least one "selected" application
    placement_rate_pct: float  # placed_students / total_students, 0 if no students
    total_categories: int
    total_questions: int
    total_assessments: int
    total_attempts: int
    submitted_attempts: int
    # Mean percentage across submitted attempts that have nonzero maximum
    # marks. None (not 0.0) when no attempt qualifies, so "no data" is never
    # displayed as a real score of zero.
    average_score_pct: float | None = None
    skill_mastery_overview: list[SkillMasteryOverview]
    # Additive dashboard fields. Defaults keep every existing consumer and
    # response fixture valid while the new overview charts use them.
    total_admins: int = 0
    user_role_counts: list[AdminUserRoleCount] = Field(default_factory=list)
    # Provenance counts so the overview can disclose demo data instead of
    # presenting it as genuine institutional activity.
    synthetic_students: int = 0
    synthetic_applications: int = 0
    department_student_counts: list[AdminDepartmentStudentCount] = Field(default_factory=list)


class AdminActivityResponse(BaseModel):
    """Admin overview activity: user distribution, departments and monthly
    new-account / new-drive / application counts."""

    user_distribution: list[AdminUserRoleCount]
    total_users: int
    department_student_counts: list[AdminDepartmentStudentCount]
    monthly_activity: list[AdminActivityMonthPoint]


# ---------------------------------------------------------------------------
# Role-specific dashboard analytics (student / TPO / admin overview charts)
#
# Every value below is computed from persisted domain records. No synthetic
# series, no hard-coded sample data, and no inference of "completed" work from
# an in-progress attempt or an application that was merely submitted.
# ---------------------------------------------------------------------------


class StudentApplicationStatusCounts(BaseModel):
    applied: int = 0
    shortlisted: int = 0
    rejected: int = 0
    selected: int = 0


class StudentDomainScore(BaseModel):
    """One of the five placement domains, scored from graded answers only."""

    domain: str
    score_pct: float  # difficulty-weighted marks / maximum marks, 0-100
    correct: int
    answered: int


class StudentAssessmentTrendPoint(BaseModel):
    """One submitted, graded assessment attempt in chronological order."""

    attempt_id: str
    assessment_id: str
    assessment_title: str
    submitted_at: datetime
    score_pct: float
    correct: int
    answered: int


class StudentAnalyticsResponse(BaseModel):
    applications: StudentApplicationStatusCounts
    total_applications: int
    # Every rate uses the student's own total applications as the denominator;
    # zero denominators return 0.0.
    applied_rate_pct: float = 0.0
    shortlisting_rate_pct: float = 0.0
    rejection_rate_pct: float = 0.0
    domain_scores: list[StudentDomainScore]
    assessment_trend: list[StudentAssessmentTrendPoint]
    submitted_attempt_count: int
    # Mean of the student's graded submitted attempts. None (not 0.0) when the
    # student has no graded attempt, so "no data" is never shown as a score.
    average_score_pct: float | None = None
    # Legacy "selected" rows mapped into ``shortlisted`` for the current
    # three-status view. Audit-only; not rendered.
    legacy_selected: int = 0


class TpoDepartmentStatusCounts(BaseModel):
    department: str
    applied: int
    shortlisted: int
    rejected: int
    total: int


class TpoMonthlyApplicationPoint(BaseModel):
    month: str  # "YYYY-MM"
    applied: int
    shortlisted: int
    rejected: int
    total: int


class TpoCompanyApplicationCounts(BaseModel):
    company_id: str | None = None
    company_name: str
    applied: int
    shortlisted: int
    rejected: int
    total: int


class TpoDriveApplicationCounts(BaseModel):
    """Application status split for ONE of the TPO's drives.

    Only drives that actually received applications in the filtered window are
    included, so a drive is never shown with an invented zero row.
    """

    drive_id: str
    job_title: str
    company_id: str | None = None
    company_name: str
    drive_status: str
    applied: int
    shortlisted: int
    rejected: int
    total: int


class TpoApplicationRecordEntry(BaseModel):
    """One application row for the click-through detail table.

    Deliberately excludes contact details, resumes and assessment answers:
    the dashboard drill-down needs identity + outcome, not private data.
    """

    application_id: str
    student_id: str
    student_name: str
    department: str | None = None
    drive_id: str
    job_title: str
    company_id: str | None = None
    company_name: str
    status: str
    applied_at: datetime
    is_synthetic: bool = False


class TpoApplicationRecordsResponse(BaseModel):
    total: int
    page: int
    limit: int
    entries: list[TpoApplicationRecordEntry]


class TpoApplicationAnalyticsResponse(BaseModel):
    total_applications: int
    total_drives: int
    date_from: date | None = None
    date_to: date | None = None
    status_breakdown: TpoApplicationStatusBreakdown
    # Distinct students, not application rows. An applicant who applied to
    # several drives is counted once. ``students_with_applications`` is the
    # user-facing name; the legacy field is kept for older clients.
    unique_applicants: int = 0
    students_with_applications: int = 0
    # Dashboard KPIs: distinct applicants and currently open drives owned by
    # this TPO. ``active_drives`` is not date-filtered (drive status is a
    # current fact, not an application event).
    total_students: int = 0
    active_drives: int = 0
    # Legacy "selected" rows mapped into ``shortlisted`` for this view.
    legacy_selected: int = 0
    # Number of applications in this view that are flagged synthetic.
    synthetic_application_count: int = 0
    # Denominators are total_applications; all are zero-safe.
    applied_rate_pct: float = 0.0
    shortlisting_rate_pct: float = 0.0
    rejection_rate_pct: float = 0.0
    departments: list[TpoDepartmentStatusCounts]
    monthly_trend: list[TpoMonthlyApplicationPoint]
    companies: list[TpoCompanyApplicationCounts]
    company_count: int  # distinct companies BEFORE top_n truncation
    company_sort: str
    top_n: int
    drives: list[TpoDriveApplicationCounts] = Field(default_factory=list)
    drive_count: int = 0  # drives with at least one application in this view
    # Aggregate radar across this TPO's drive assessments, computed from real
    # graded answers only. Empty when no graded attempt exists.
    domain_scores: list[StudentDomainScore] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Admin applications workspace
# ---------------------------------------------------------------------------


class AdminApplicationSummary(BaseModel):
    """Status cards for the admin applications workspace.

    Computed over the population matching every filter EXCEPT the status
    filter, so all four cards stay meaningful while a status filter is active.
    """

    total: int = 0
    applied: int = 0
    shortlisted: int = 0
    rejected: int = 0
    legacy_selected: int = 0


class AdminApplicationEntry(BaseModel):
    """One application row across every drive, for the admin workspace.

    Carries identity + outcome only (no contact details, resumes or answers).
    ``rank`` is the student's standing in the drive's required assessment,
    computed from the same best-submitted-attempt rule as the TPO ranking.
    """

    application_id: str
    student_id: str
    student_name: str
    department: str | None = None
    company_id: str | None = None
    company_name: str
    drive_id: str
    job_title: str
    assessment_id: str | None = None
    assessment_title: str | None = None
    assessment_status: str = "not_required"
    assessment_score_pct: float | None = None
    rank: int | None = None
    status: str
    applied_at: datetime
    is_synthetic: bool = False


class AdminApplicationRecordsResponse(BaseModel):
    total: int
    page: int
    limit: int
    summary: AdminApplicationSummary
    entries: list[AdminApplicationEntry]


class AdminApplicationFilterCompany(BaseModel):
    id: str
    name: str


class AdminApplicationFilterDrive(BaseModel):
    id: str
    job_title: str
    company_name: str
    status: str


class AdminApplicationFiltersResponse(BaseModel):
    companies: list[AdminApplicationFilterCompany]
    drives: list[AdminApplicationFilterDrive]
    departments: list[str]


# ---------------------------------------------------------------------------
# Phase 8 — TPO Skill Gap Analysis
#
# Two independent student-skill evidence sources, never merged:
#
# - Assessment-demonstrated: recomputed per skill from SUBMITTED attempts on
#   placement drives' required assessments only (the
#   Placement Drive -> Required Assessment -> Attempt -> Student chain).
#   Practice attempts can never contribute because only assessments referenced
#   by a drive's ``required_assessment_id`` are ever fetched. The existing
#   ``knowledge_states`` collection is deliberately NOT used as a source —
#   knowledge tracing is updated for practice attempts too, so it would leak
#   practice performance into drive-skill evidence.
# - Self-reported: the student profile's structured ``skills`` list and the
#   ACTIVE resume's extracted ``skill_set``. A self-reported skill is never
#   counted as demonstrated proficiency — the two perspectives are reported
#   side by side (demonstrated gap vs reported gap).
#
# Industry demand comes from the existing Market Insights dataset
# (``job_market_postings`` + ``market_skill_catalog``) with the SAME filter
# semantics and window math as the market dashboard.
# ---------------------------------------------------------------------------

AssessmentEvidenceClass = Literal[
    "demonstrated", "developing", "not_demonstrated", "insufficient_evidence"
]

# The student-facing classification of ONE skill for ONE student: the
# strongest available evidence. ``both`` = self-reported AND assessed with
# enough graded answers to classify (the proficiency level itself is carried
# by ``assessment_classification``/accuracy). A student who reports the skill
# but has too few graded answers is ``reported_only`` — insufficient attempt
# evidence is never promoted to "both".
StudentSkillGapClass = Literal[
    "both",
    "demonstrated",
    "developing",
    "not_demonstrated",
    "reported_only",
    "insufficient_evidence",
    "no_evidence",
]

PriorityClass = Literal["high", "medium", "low"]

SkillGapStudentFilter = Literal[
    "all",
    "both",
    "demonstrated",
    "developing",
    "not_demonstrated",
    "reported_only",
    "insufficient_evidence",
    "no_evidence",
]

SkillGapSort = Literal["priority", "demand", "gap"]


class SkillGapThresholds(BaseModel):
    """The exact constants the skill-gap math used — exposed so the UI can
    explain every classification instead of presenting arbitrary numbers."""

    min_graded_answers: int
    demonstrated_min_pct: float
    developing_min_pct: float
    priority_weights: dict[str, float]
    priority_class_thresholds: dict[str, float]


class StudentEvidenceSource(BaseModel):
    """One eligible drive assessment's contribution to ONE student's evidence
    for ONE skill — the only assessment detail the skill-gap views expose."""

    assessment_title: str
    attempts_used: int
    questions_answered: int
    correct_answers: int


class SkillCompanyDemand(BaseModel):
    """How many of ONE company's (filtered) postings demand the skill."""

    company_slug: str
    company_name: str
    posting_count: int
    demand_pct: float  # share of that company's own postings


class SkillJobFamilyDemand(BaseModel):
    """How many of ONE job family's (filtered) postings demand the skill."""

    job_family: str
    posting_count: int
    demand_pct: float  # share of that family's own postings


class SkillYearDemand(BaseModel):
    """One year of a skill's demand series (calendar-year counts for display;
    growth is always computed between comparable windows, like the market
    dashboard's historical series)."""

    year: int
    posting_count: int
    demand_pct: float
    yoy_growth_pct: float | None = None


class SkillGapEntry(BaseModel):
    """One demanded skill: industry demand + student evidence + gap result."""

    skill_id: str  # catalog slug (or slugified name when not in the catalog)
    name: str
    category: str | None
    is_technical: bool

    # --- Industry demand (Market Insights dataset, filtered population) ---
    posting_count: int
    demand_pct: float  # share of ALL filtered postings
    demanding_company_count: int
    demanding_job_family_count: int
    yearly_counts: dict[int, int]
    yearly_demand_pct: dict[int, float]
    latest_growth_pct: float | None  # comparable-window growth, None if unavailable
    growth_comparable: bool

    # --- Student evidence (aggregated over the student population) ---
    students_demonstrated: int  # strongly demonstrated (>= demonstrated_min_pct)
    students_developing: int
    students_not_demonstrated: int  # classified, but below developing_min_pct
    students_insufficient_evidence: int  # graded answers < min_graded_answers
    students_reported: int  # self-reported (profile and/or active resume)
    students_reported_only: int  # self-reported, without classified assessment evidence
    students_both: int  # self-reported AND classified assessment evidence
    students_no_evidence: int  # neither reported nor any graded attempt evidence
    students_lacking_demonstrated: int  # population - students_demonstrated

    demonstrated_pct: float  # students_demonstrated / population
    reported_pct: float
    gap_pct: float  # students_lacking_demonstrated / population

    # --- Gap result ---
    priority_score: float
    priority_class: PriorityClass

    # --- Detail views (bounded; everything from the same aggregation pass) ---
    top_companies: list[SkillCompanyDemand]
    top_job_families: list[SkillJobFamilyDemand]
    years: list[SkillYearDemand]


class MostDemandedMissingSkill(BaseModel):
    skill_id: str
    name: str
    posting_count: int
    demand_pct: float


class RisingDemandSkill(BaseModel):
    """A skill whose comparable demand is growing while demonstrated student
    proficiency is low — the demand-growth gap the summary card surfaces."""

    skill_id: str
    name: str
    latest_growth_pct: float
    demand_pct: float
    demonstrated_pct: float


class SkillGapSummary(BaseModel):
    total_skills_analyzed: int
    high_priority_gaps: int
    student_population: int
    # Students with NO strongly-demonstrated skill across the whole analysis.
    students_lacking_demonstrated_skills: int
    students_with_reported_skills: int
    students_with_assessment_evidence: int
    # The most demanded skill zero students have demonstrated (None when every
    # demanded skill has at least one demonstrated student).
    most_demanded_missing_skill: MostDemandedMissingSkill | None = None
    rising_demand_skills: list[RisingDemandSkill] = []


class SkillGapMeta(BaseModel):
    """Dataset identity + evidence-coverage explanation for the response."""

    market: MarketMeta  # same metadata block the market dashboard returns
    thresholds: SkillGapThresholds
    eligible_drive_count: int  # drives whose required assessment contributed
    eligible_assessment_count: int  # distinct required assessments used
    submitted_eligible_attempt_count: int  # submitted attempts actually used
    unmapped_assessment_skill_tags: list[str]  # question tags with no catalog/market mapping
    unmapped_self_reported_skills: list[str]  # reported skills with no mapping
    notes: list[str]


class SkillGapAnalysisResponse(BaseModel):
    meta: SkillGapMeta
    summary: SkillGapSummary
    skills: list[SkillGapEntry]


class SkillGapStudentEntry(BaseModel):
    """One student's relationship to ONE demanded skill.

    Analytics-only projection: name, department, batch year and the evidence
    relevant to THIS skill — never emails, resumes, phone numbers, or
    assessment data unrelated to the selected skill."""

    student_id: str  # student PROFILE id (same id space as applications)
    student_name: str
    department: str | None
    batch_year: int | None
    self_reported: bool
    self_reported_via: list[str]  # "profile" and/or "resume"
    classification: StudentSkillGapClass
    assessment_classification: AssessmentEvidenceClass | None = None
    skill_accuracy_pct: float | None = None  # None when insufficient/no evidence
    questions_answered: int
    correct_answers: int
    assessment_evidence: list[StudentEvidenceSource]


class SkillGapStudentsResponse(BaseModel):
    skill_id: str
    skill_name: str
    classification: SkillGapStudentFilter  # echo of the filter applied
    student_population: int
    total: int  # rows matching the filter+search across all pages
    page: int
    limit: int
    entries: list[SkillGapStudentEntry]
