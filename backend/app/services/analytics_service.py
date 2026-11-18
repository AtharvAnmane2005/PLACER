import re
from collections import defaultdict
from datetime import date, datetime, time

from bson import ObjectId

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.departments import department_label as _normalize_department
from app.models.analytics import (
    AdminActivityMonthPoint,
    AdminActivityResponse,
    AdminAnalyticsResponse,
    AdminApplicationEntry,
    AdminApplicationFilterCompany,
    AdminApplicationFilterDrive,
    AdminApplicationFiltersResponse,
    AdminApplicationRecordsResponse,
    AdminApplicationSummary,
    AdminDepartmentStudentCount,
    AdminUserRoleCount,
    ApplicationStatusBreakdown,
    DriveApplicantEntry,
    DriveApplicantsResponse,
    DriveAssessmentRanking,
    DriveAssessmentRankingEntry,
    DriveFunnel,
    DriveParticipantEntry,
    DriveParticipantsResponse,
    SkillMasteryOverview,
    StudentAnalyticsResponse,
    StudentApplicationStatusCounts,
    StudentAssessmentTrendPoint,
    StudentDomainScore,
    TpoAnalyticsResponse,
    TpoApplicationAnalyticsResponse,
    TpoApplicationRecordEntry,
    TpoApplicationRecordsResponse,
    TpoApplicationStatusBreakdown,
    TpoCompanyApplicationCounts,
    TpoDepartmentStatusCounts,
    TpoDriveApplicationCounts,
    TpoMonthlyApplicationPoint,
)
from app.models.assessment import (
    DIFFICULTY_MARKS,
    PLACEMENT_SECTIONS,
    AttemptStatus,
    DifficultyLevel,
)
from app.models.drive import PlacementDriveInDB
from app.repositories.application_repository import ApplicationRepository
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.attempt_repository import AttemptRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.drive_repository import PlacementDriveRepository
from app.repositories.knowledge_state_repository import KnowledgeStateRepository
from app.repositories.profile_repositories import StudentRepository, TPORepository
from app.repositories.question_repository import QuestionCategoryRepository, QuestionRepository
from app.repositories.user_repository import UserRepository

# Generous but finite caps on "fetch everything" queries — this project's
# scale (a college placement cell, not a SaaS product) means these won't
# be hit in practice, but an unbounded find_many() against a collection
# that could theoretically grow unboundedly is still worth capping.
_ANALYTICS_FETCH_LIMIT = 5000

# Hard cap on how many student profiles a name search may match before the
# filter is applied to the applicant/participant query. Far above any real
# cohort; exists so a pathological one-character search can't stream the
# whole students collection into memory.
_SEARCH_STUDENT_CAP = 1000


class AnalyticsError(Exception):
    """Raised by analytics endpoints; carries an HTTP status code."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _empty_breakdown() -> ApplicationStatusBreakdown:
    return ApplicationStatusBreakdown(applied=0, shortlisted=0, rejected=0, selected=0)


# The current workflow has exactly three statuses. Legacy ``selected`` rows
# are read-time mapped to ``shortlisted`` so Applied + Shortlisted + Rejected
# always equals the total and no dashboard invents a Selected stage. The
# underlying documents are never modified by analytics.
_LEGACY_STATUS_MAP = {"selected": "shortlisted"}


def _effective_status(value) -> str:
    status = value.value if hasattr(value, "value") else str(value)
    return _LEGACY_STATUS_MAP.get(status, status)


def _tally(applications) -> ApplicationStatusBreakdown:
    """Full breakdown for admin/student views.

    ``selected`` is always 0 in the current analytics; legacy selected rows
    are counted as ``shortlisted`` (see :func:`_legacy_selected_count`).
    """
    counts = {"applied": 0, "shortlisted": 0, "rejected": 0}
    for app in applications:
        status = _effective_status(app.status)
        if status in counts:
            counts[status] += 1
    return ApplicationStatusBreakdown(
        applied=counts["applied"],
        shortlisted=counts["shortlisted"],
        rejected=counts["rejected"],
        selected=0,
    )


def _legacy_selected_count(applications) -> int:
    """Audit-only count of legacy selected rows mapped into shortlisted."""
    return sum(1 for app in applications if _status_value(app.status) == "selected")


def _empty_tpo_breakdown() -> TpoApplicationStatusBreakdown:
    return TpoApplicationStatusBreakdown(applied=0, shortlisted=0, rejected=0)


def _tally_tpo(applications) -> TpoApplicationStatusBreakdown:
    """Count the three statuses a TPO manages.

    Legacy ``selected`` applications are mapped into ``shortlisted`` (the
    closest current outcome) instead of being dropped, so the breakdown always
    reconciles with ``total_applications``. The records themselves are
    untouched and remain visible to admins.
    """
    counts = {"applied": 0, "shortlisted": 0, "rejected": 0}
    for app in applications:
        status = _effective_status(app.status)
        if status in counts:
            counts[status] += 1
    return TpoApplicationStatusBreakdown(**counts)


def _rate_pct(numerator: int, denominator: int) -> float:
    """Zero-safe percentage. A missing denominator is 0%, never a divide error."""
    return round(100.0 * numerator / denominator, 1) if denominator > 0 else 0.0


def _attempt_score_pct(attempt) -> float:
    """Score percentage for a submitted attempt, reconstructed from the
    difficulty-at-time marks (see DIFFICULTY_MARKS). Returns 0.0 when the
    attempt answered nothing."""
    total_marks = sum(ans.marks_awarded for ans in attempt.answers)
    max_marks = sum(DIFFICULTY_MARKS[ans.difficulty_at_time] for ans in attempt.answers)
    return round(100.0 * total_marks / max_marks, 1) if max_marks > 0 else 0.0


def _name_search_regex(search: str) -> str:
    """Case-insensitive substring matcher, escaped so a search string can
    never inject regex operators into the query."""
    return re.compile(re.escape(search), re.IGNORECASE)


# ---------------------------------------------------------------------------
# Shared dashboard aggregation helpers
# ---------------------------------------------------------------------------

_MONTH_KEY_FORMAT = "%Y-%m"

# A trend longer than this is unreadable in a dashboard chart and would mean
# an absurdly wide date range. Implicit ranges keep the most recent window;
# an explicitly requested wider range is rejected with a clear error.
_MAX_TREND_MONTHS = 120

# Legacy assessments have no ``sections`` metadata. These keyword groups map
# a real question's category / skill tags / topic onto the same five domains
# the standardized assessments use. They are attribution rules, not invented
# data: a question that matches nothing is attributed by its real type.
_DOMAIN_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Quantitative Aptitude",
        (
            "quantitative",
            "aptitude",
            "math",
            "mathematics",
            "numerical",
            "probability",
            "statistics",
            "algebra",
            "geometry",
            "ratio",
            "percentage",
        ),
    ),
    (
        "Logical Reasoning",
        (
            "logical",
            "reasoning",
            "puzzle",
            "analytical",
            "series",
            "coding-decoding",
            "blood relation",
            "syllogism",
            "arrangement",
        ),
    ),
    (
        "Verbal Ability",
        (
            "verbal",
            "english",
            "grammar",
            "vocabulary",
            "comprehension",
            "synonym",
            "antonym",
            "reading",
        ),
    ),
    (
        "Programming / Problem Solving",
        (
            "programming",
            "coding",
            "algorithm",
            "data structure",
            "object-oriented",
            "oop",
            "python",
            "java",
            "javascript",
            "typescript",
            "c++",
            "c#",
            "web development",
            "problem solving",
            "recursion",
            "dynamic programming",
            "sql",
            "database",
        ),
    ),
    (
        "Technical Knowledge",
        (
            "technical",
            "dbms",
            "operating system",
            "computer network",
            "networking",
            "software engineering",
            "system design",
            "cloud",
            "security",
        ),
    ),
)


def _status_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _month_key(value: datetime) -> str:
    return value.strftime(_MONTH_KEY_FORMAT)


def _recorded_at(record, field: str = "created_at") -> datetime | None:
    """Return the document's real creation time, or ``None`` if unknowable.

    Pydantic fills model defaults for missing fields, so ``getattr`` alone
    would present a legacy record with no timestamp as if it had just been
    created. ``model_fields_set`` distinguishes a stored value from a default.

    When the timestamp was never stored, fall back to the MongoDB ObjectId's
    embedded creation time. That is still the document's own insert time
    (not an estimate), so legacy records keep their true month instead of
    disappearing from every trend.
    """
    if field in getattr(record, "model_fields_set", set()):
        value = getattr(record, field, None)
        if isinstance(value, datetime):
            return value
    record_id = getattr(record, "id", None)
    if isinstance(record_id, str) and ObjectId.is_valid(record_id):
        return ObjectId(record_id).generation_time
    return None


def _month_start(key: str) -> date:
    year, month = key.split("-")
    return date(int(year), int(month), 1)


def _add_months(value: date, delta: int) -> date:
    index = value.year * 12 + (value.month - 1) + delta
    return date(index // 12, index % 12 + 1, 1)


def _month_keys(start: date, end: date, *, max_months: int = _MAX_TREND_MONTHS) -> list[str]:
    """Every month from ``start`` to ``end`` inclusive, zero-fill friendly."""
    if end < start:
        return []
    keys: list[str] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        keys.append(cursor.strftime(_MONTH_KEY_FORMAT))
        if len(keys) > max_months:
            raise AnalyticsError(
                f"Date range is too wide for a monthly trend (maximum {max_months} months).",
                400,
            )
        cursor = _add_months(cursor, 1)
    return keys


def _clamped_month_keys(start: date, end: date) -> list[str]:
    """Implicit-range variant: keep the most recent readable window instead of
    rejecting data that simply spans many years."""
    if end < start:
        return []
    span = (end.year - start.year) * 12 + (end.month - start.month)
    if span >= _MAX_TREND_MONTHS:
        start = _add_months(end, -(_MAX_TREND_MONTHS - 1))
    return _month_keys(start, end)


def _graded_answers(attempt) -> list:
    """Answers with an actual grade. ``None`` means an ungraded descriptive
    answer and must never be treated as wrong or as evidence of completion."""
    return [answer for answer in attempt.answers if answer.is_correct is not None]


def _graded_attempt_score_pct(attempt) -> tuple[float, int, int]:
    """(score_pct, correct_count, answered_count) over graded answers only.

    Uses the same difficulty-at-time weights as ``_attempt_score_pct`` so the
    dashboard trend and the attempt result page agree, while excluding
    ungraded descriptive answers and empty submitted attempts.
    """
    graded = _graded_answers(attempt)
    total_marks = sum(answer.marks_awarded for answer in graded)
    max_marks = sum(DIFFICULTY_MARKS[answer.difficulty_at_time] for answer in graded)
    correct = sum(1 for answer in graded if answer.is_correct is True)
    score = round(100.0 * total_marks / max_marks, 1) if max_marks > 0 else 0.0
    return score, correct, len(graded)


def _keyword_matches(haystack: str, keyword: str) -> bool:
    if any(character in keyword for character in " +/#-"):
        return keyword in haystack
    return re.search(rf"\b{re.escape(keyword)}\b", haystack) is not None


def _section_domain_map(assessment) -> dict[str, str]:
    """question_id -> canonical placement section, for standardized assessments.

    Only the five canonical section names are accepted; an unrecognised
    section name falls through to the legacy heuristics rather than inventing
    a sixth radar axis.
    """
    mapping: dict[str, str] = {}
    for section in assessment.sections or []:
        if not isinstance(section, dict):
            continue
        name = section.get("name")
        if not isinstance(name, str) or name not in PLACEMENT_SECTIONS:
            continue
        for question_id in section.get("question_ids") or []:
            mapping[str(question_id)] = name
    return mapping


def _domain_for_question(
    question,
    section_name: str | None,
    category_name: str | None,
) -> str | None:
    """Attribute one real answer to a placement domain.

    The assessment's own section metadata is authoritative. Legacy attempts
    fall back to the question's category / tags / topic, then to its actual
    question type. ``None`` means the question no longer exists and no
    section metadata names it, so it cannot be attributed honestly.
    """
    if section_name in PLACEMENT_SECTIONS:
        return section_name
    if not question:
        return None

    parts: list[str] = []
    if category_name:
        parts.append(category_name)
    parts.extend(question.skill_tags or [])
    if question.skill:
        parts.append(question.skill)
    if question.topic:
        parts.append(question.topic)
    question_type = question.type.value if hasattr(question.type, "value") else str(question.type)
    parts.append(question_type)
    haystack = " ".join(parts).lower()

    for domain, keywords in _DOMAIN_KEYWORDS:
        if any(_keyword_matches(haystack, keyword) for keyword in keywords):
            return domain
    if question_type == "coding":
        return "Programming / Problem Solving"
    return "Technical Knowledge"


def _empty_tpo_application_analytics(
    *,
    total_drives: int,
    date_from: date | None,
    date_to: date | None,
    top_n: int,
    company_sort: str,
) -> TpoApplicationAnalyticsResponse:
    return TpoApplicationAnalyticsResponse(
        total_applications=0,
        total_drives=total_drives,
        date_from=date_from,
        date_to=date_to,
        status_breakdown=_empty_tpo_breakdown(),
        departments=[],
        monthly_trend=[],
        companies=[],
        company_count=0,
        company_sort=company_sort,
        top_n=top_n,
    )


class AnalyticsService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.drives = PlacementDriveRepository(db)
        self.applications = ApplicationRepository(db)
        self.companies = CompanyRepository(db)
        self.students = StudentRepository(db)
        self.tpos = TPORepository(db)
        self.categories = QuestionCategoryRepository(db)
        self.questions = QuestionRepository(db)
        self.assessments = AssessmentRepository(db)
        self.attempts = AttemptRepository(db)
        self.knowledge_states = KnowledgeStateRepository(db)
        self.users = UserRepository(db)

    async def get_tpo_analytics(self, tpo_user_id: str) -> TpoAnalyticsResponse:
        tpo = await self.tpos.get_by_user_id(tpo_user_id)
        if not tpo:
            drives = []
        else:
            drives = await self.drives.find_many({"created_by": tpo.id}, limit=_ANALYTICS_FETCH_LIMIT)

        # One batched company lookup instead of one per drive. Document ids
        # are ObjectIds in storage; profile references (company_id on the
        # drive) are stored as strings, so only _id queries need conversion.
        company_ids = {str(drive.company_id) for drive in drives}
        companies = await self.companies.find_many(
            {"_id": {"$in": [ObjectId(cid) for cid in company_ids]}}, limit=_ANALYTICS_FETCH_LIMIT
        ) if company_ids else []
        company_names = {company.id: company.name for company in companies}

        drive_funnels: list[DriveFunnel] = []
        overall = _empty_tpo_breakdown()
        open_count = 0
        closed_count = 0
        synthetic_application_count = 0

        for drive in drives:
            if drive.status == "open":
                open_count += 1
            else:
                closed_count += 1

            applications = await self.applications.find_many({"drive_id": drive.id}, limit=_ANALYTICS_FETCH_LIMIT)
            breakdown = _tally_tpo(applications)
            synthetic_application_count += sum(1 for app in applications if app.is_synthetic)
            eligible_count = sum(1 for app in applications if app.eligibility_passed is not False)
            for field in ("applied", "shortlisted", "rejected"):
                setattr(overall, field, getattr(overall, field) + getattr(breakdown, field))

            company_name = company_names.get(str(drive.company_id), "Unknown company")

            # Participation counts for the drive overview. The attempt pool is
            # the drive's required assessment, scoped to the drive's own
            # applicants — see _drive_attempt_pool for why.
            assessment_title = None
            participant_count = 0
            submitted_count = 0
            if drive.required_assessment_id:
                assessment = await self.assessments.get_by_id(str(drive.required_assessment_id))
                if assessment:
                    assessment_title = assessment.title
                    applicant_ids = {app.student_id for app in applications}
                    attempts = await self.attempts.find_many(
                        {"assessment_id": assessment.id}, limit=_ANALYTICS_FETCH_LIMIT
                    )
                    participants = {
                        attempt.student_id
                        for attempt in attempts
                        if attempt.student_id in applicant_ids
                    }
                    participant_count = len(participants)
                    submitted_count = len({
                        attempt.student_id
                        for attempt in attempts
                        if attempt.student_id in applicant_ids
                        and attempt.status == AttemptStatus.SUBMITTED
                    })

            drive_funnels.append(
                DriveFunnel(
                    drive_id=drive.id,
                    job_title=drive.job_title,
                    company_name=company_name,
                    status=drive.status.value if hasattr(drive.status, "value") else drive.status,
                    total_applications=len(applications),
                    breakdown=breakdown,
                    required_assessment_id=str(drive.required_assessment_id) if drive.required_assessment_id else None,
                    assessment_title=assessment_title,
                    participant_count=participant_count,
                    submitted_participant_count=submitted_count,
                    eligible_application_count=eligible_count,
                    completion_rate_pct=_rate_pct(submitted_count, eligible_count),
                )
            )

        total_applications = overall.applied + overall.shortlisted + overall.rejected

        return TpoAnalyticsResponse(
            total_drives=len(drives),
            open_drives=open_count,
            closed_drives=closed_count,
            total_applications=total_applications,
            breakdown=overall,
            drives=drive_funnels,
            synthetic_application_count=synthetic_application_count,
        )

    async def _domain_scores_for_attempts(self, attempts) -> list[StudentDomainScore]:
        """Aggregate the five placement domains from real graded answers.

        Used by the TPO's aggregate radar. The same attribution rules as the
        student radar apply: an assessment's own section metadata is
        authoritative, legacy questions fall back to their real category /
        tags / type, and ungraded descriptive answers are excluded.
        """
        submitted = [
            attempt for attempt in attempts if attempt.status == AttemptStatus.SUBMITTED
        ]
        assessment_ids = {str(attempt.assessment_id) for attempt in submitted}
        valid_assessment_ids = [
            ObjectId(value) for value in assessment_ids if ObjectId.is_valid(value)
        ]
        assessments = (
            {
                assessment.id: assessment
                for assessment in await self.assessments.find_many(
                    {"_id": {"$in": valid_assessment_ids}}, limit=len(valid_assessment_ids)
                )
            }
            if valid_assessment_ids
            else {}
        )

        question_ids = {
            answer.question_id for attempt in submitted for answer in attempt.answers
        }
        valid_question_ids = [ObjectId(value) for value in question_ids if ObjectId.is_valid(value)]
        questions = (
            {
                question.id: question
                for question in await self.questions.find_many(
                    {"_id": {"$in": valid_question_ids}}, limit=len(valid_question_ids)
                )
            }
            if valid_question_ids
            else {}
        )

        category_ids = {question.category_id for question in questions.values()}
        valid_category_ids = [ObjectId(value) for value in category_ids if ObjectId.is_valid(value)]
        categories = (
            {
                category.id: category.name
                for category in await self.categories.find_many(
                    {"_id": {"$in": valid_category_ids}}, limit=len(valid_category_ids)
                )
            }
            if valid_category_ids
            else {}
        )

        awarded_by_domain = {domain: 0.0 for domain in PLACEMENT_SECTIONS}
        maximum_by_domain = {domain: 0.0 for domain in PLACEMENT_SECTIONS}
        correct_by_domain = {domain: 0 for domain in PLACEMENT_SECTIONS}
        answered_by_domain = {domain: 0 for domain in PLACEMENT_SECTIONS}

        for attempt in submitted:
            graded = _graded_answers(attempt)
            if not graded:
                continue
            assessment = assessments.get(str(attempt.assessment_id))
            section_map = _section_domain_map(assessment) if assessment else {}
            for answer in graded:
                question = questions.get(answer.question_id)
                category_name = categories.get(question.category_id) if question else None
                domain = _domain_for_question(
                    question,
                    section_map.get(answer.question_id),
                    category_name,
                )
                if domain is None:
                    continue
                awarded_by_domain[domain] += answer.marks_awarded
                maximum_by_domain[domain] += DIFFICULTY_MARKS[answer.difficulty_at_time]
                answered_by_domain[domain] += 1
                if answer.is_correct is True:
                    correct_by_domain[domain] += 1

        if not any(answered_by_domain.values()):
            # No graded evidence: return an empty series so the UI can show an
            # explicit empty state instead of a radar of five zero scores.
            return []

        return [
            StudentDomainScore(
                domain=domain,
                score_pct=round(
                    100.0 * awarded_by_domain[domain] / maximum_by_domain[domain], 1
                )
                if maximum_by_domain[domain] > 0
                else 0.0,
                correct=correct_by_domain[domain],
                answered=answered_by_domain[domain],
            )
            for domain in PLACEMENT_SECTIONS
        ]

    async def get_student_analytics(self, student_user_id: str) -> StudentAnalyticsResponse:
        """A student's own dashboard analytics.

        Scoped to the authenticated student's profile id. Only SUBMITTED
        attempts with at least one graded answer contribute to the domain
        radar or the score trend; an empty submitted attempt is not a
        completed assessment and is deliberately excluded.
        """
        student = await self.students.get_by_user_id(student_user_id)
        if not student:
            raise AnalyticsError("Student profile not found.", 404)

        applications = await self.applications.find_many(
            {"student_id": student.id}, limit=_ANALYTICS_FETCH_LIMIT
        )
        breakdown = _tally(applications)

        raw_attempts = await self.attempts.get_for_student(student.id)
        submitted = [
            attempt for attempt in raw_attempts if attempt.status == AttemptStatus.SUBMITTED
        ]

        # Batch-load every assessment, question and category referenced by the
        # submitted attempts. One round-trip per collection, not per answer.
        assessment_ids = {str(attempt.assessment_id) for attempt in submitted}
        valid_assessment_ids = [
            ObjectId(value) for value in assessment_ids if ObjectId.is_valid(value)
        ]
        assessments = (
            {
                assessment.id: assessment
                for assessment in await self.assessments.find_many(
                    {"_id": {"$in": valid_assessment_ids}}, limit=len(valid_assessment_ids)
                )
            }
            if valid_assessment_ids
            else {}
        )

        question_ids = {
            answer.question_id for attempt in submitted for answer in attempt.answers
        }
        valid_question_ids = [ObjectId(value) for value in question_ids if ObjectId.is_valid(value)]
        questions = (
            {
                question.id: question
                for question in await self.questions.find_many(
                    {"_id": {"$in": valid_question_ids}}, limit=len(valid_question_ids)
                )
            }
            if valid_question_ids
            else {}
        )

        category_ids = {question.category_id for question in questions.values()}
        valid_category_ids = [ObjectId(value) for value in category_ids if ObjectId.is_valid(value)]
        categories = (
            {
                category.id: category.name
                for category in await self.categories.find_many(
                    {"_id": {"$in": valid_category_ids}}, limit=len(valid_category_ids)
                )
            }
            if valid_category_ids
            else {}
        )

        awarded_by_domain = {domain: 0.0 for domain in PLACEMENT_SECTIONS}
        maximum_by_domain = {domain: 0.0 for domain in PLACEMENT_SECTIONS}
        correct_by_domain = {domain: 0 for domain in PLACEMENT_SECTIONS}
        answered_by_domain = {domain: 0 for domain in PLACEMENT_SECTIONS}
        trend: list[StudentAssessmentTrendPoint] = []

        for attempt in submitted:
            graded = _graded_answers(attempt)
            if not graded:
                continue

            assessment = assessments.get(str(attempt.assessment_id))
            section_map = _section_domain_map(assessment) if assessment else {}

            for answer in graded:
                question = questions.get(answer.question_id)
                category_name = categories.get(question.category_id) if question else None
                domain = _domain_for_question(
                    question,
                    section_map.get(answer.question_id),
                    category_name,
                )
                if domain is None:
                    continue
                awarded_by_domain[domain] += answer.marks_awarded
                maximum_by_domain[domain] += DIFFICULTY_MARKS[answer.difficulty_at_time]
                answered_by_domain[domain] += 1
                if answer.is_correct is True:
                    correct_by_domain[domain] += 1

            score, correct, answered = _graded_attempt_score_pct(attempt)
            trend.append(
                StudentAssessmentTrendPoint(
                    attempt_id=attempt.id or "",
                    assessment_id=str(attempt.assessment_id),
                    assessment_title=assessment.title if assessment else "Assessment",
                    submitted_at=attempt.submitted_at or attempt.started_at,
                    score_pct=score,
                    correct=correct,
                    answered=answered,
                )
            )

        trend.sort(key=lambda point: (point.submitted_at, point.attempt_id))

        domain_scores = [
            StudentDomainScore(
                domain=domain,
                score_pct=round(
                    100.0 * awarded_by_domain[domain] / maximum_by_domain[domain], 1
                )
                if maximum_by_domain[domain] > 0
                else 0.0,
                correct=correct_by_domain[domain],
                answered=answered_by_domain[domain],
            )
            for domain in PLACEMENT_SECTIONS
        ]

        average_score = (
            round(sum(point.score_pct for point in trend) / len(trend), 1)
            if trend
            else None
        )

        return StudentAnalyticsResponse(
            applications=StudentApplicationStatusCounts(
                applied=breakdown.applied,
                shortlisted=breakdown.shortlisted,
                rejected=breakdown.rejected,
                selected=0,
            ),
            total_applications=len(applications),
            applied_rate_pct=_rate_pct(breakdown.applied, len(applications)),
            shortlisting_rate_pct=_rate_pct(breakdown.shortlisted, len(applications)),
            rejection_rate_pct=_rate_pct(breakdown.rejected, len(applications)),
            domain_scores=domain_scores,
            assessment_trend=trend,
            submitted_attempt_count=len(trend),
            average_score_pct=average_score,
            legacy_selected=_legacy_selected_count(applications),
        )

    async def get_tpo_application_analytics(
        self,
        tpo_user_id: str,
        *,
        date_from: date | None,
        date_to: date | None,
        top_n: int,
        company_sort: str,
    ) -> TpoApplicationAnalyticsResponse:
        """Application analytics for a TPO's OWN drives, with optional
        applied-date filtering, department grouping, a zero-filled monthly
        trend and a sorted Top-N company breakdown."""
        if date_from and date_to and date_from > date_to:
            raise AnalyticsError("date_from must be on or before date_to.", 400)

        tpo = await self.tpos.get_by_user_id(tpo_user_id)
        if not tpo:
            return _empty_tpo_application_analytics(
                total_drives=0,
                date_from=date_from,
                date_to=date_to,
                top_n=top_n,
                company_sort=company_sort,
            )

        drives = await self.drives.find_many({"created_by": tpo.id}, limit=_ANALYTICS_FETCH_LIMIT)
        if not drives:
            return _empty_tpo_application_analytics(
                total_drives=0,
                date_from=date_from,
                date_to=date_to,
                top_n=top_n,
                company_sort=company_sort,
            )

        drive_by_id = {drive.id: drive for drive in drives}
        query: dict = {"drive_id": {"$in": list(drive_by_id)}}
        if date_from or date_to:
            applied_range: dict = {}
            if date_from:
                applied_range["$gte"] = datetime.combine(date_from, time.min)
            if date_to:
                applied_range["$lte"] = datetime.combine(date_to, time.max)
            query["applied_at"] = applied_range

        applications = await self.applications.find_many(query, limit=_ANALYTICS_FETCH_LIMIT)
        breakdown = _tally_tpo(applications)
        applicant_student_ids = {application.student_id for application in applications}
        legacy_selected = _legacy_selected_count(applications)
        active_drives = sum(1 for drive in drives if _status_value(drive.status) == "open")

        # One batched student lookup for department grouping.
        student_ids = applicant_student_ids
        valid_student_ids = [ObjectId(value) for value in student_ids if ObjectId.is_valid(value)]
        students = (
            {
                student.id: student
                for student in await self.students.find_many(
                    {"_id": {"$in": valid_student_ids}}, limit=len(valid_student_ids)
                )
            }
            if valid_student_ids
            else {}
        )

        department_rows: dict[str, dict[str, int]] = {}
        for application in applications:
            student = students.get(application.student_id)
            department = _normalize_department(student.department if student else None)
            row = department_rows.setdefault(
                department,
                {"applied": 0, "shortlisted": 0, "rejected": 0},
            )
            status = _status_value(application.status)
            if status in row:
                row[status] += 1

        departments = [
            TpoDepartmentStatusCounts(
                department=department,
                applied=counts["applied"],
                shortlisted=counts["shortlisted"],
                rejected=counts["rejected"],
                total=sum(counts.values()),
            )
            for department, counts in sorted(
                department_rows.items(),
                key=lambda item: (-sum(item[1].values()), item[0].lower()),
            )
        ]

        month_rows: dict[str, dict[str, int]] = defaultdict(
            lambda: {"applied": 0, "shortlisted": 0, "rejected": 0}
        )
        for application in applications:
            row = month_rows[_month_key(application.applied_at)]
            status = _status_value(application.status)
            if status in row:
                row[status] += 1

        if date_from or date_to:
            application_months = sorted(_month_key(app.applied_at) for app in applications)
            start = date_from or (_month_start(application_months[0]) if application_months else None)
            end = date_to or (_month_start(application_months[-1]) if application_months else None)
            month_keys = _month_keys(start, end) if start and end else []
        elif applications:
            application_months = sorted(_month_key(app.applied_at) for app in applications)
            month_keys = _clamped_month_keys(
                _month_start(application_months[0]),
                _month_start(application_months[-1]),
            )
        else:
            month_keys = []

        monthly_trend = [
            TpoMonthlyApplicationPoint(
                month=key,
                applied=month_rows[key]["applied"],
                shortlisted=month_rows[key]["shortlisted"],
                rejected=month_rows[key]["rejected"],
                total=sum(month_rows[key].values()),
            )
            for key in month_keys
        ]

        # One batched company lookup for the company breakdown.
        company_ids = {str(drive.company_id) for drive in drives}
        valid_company_ids = [ObjectId(value) for value in company_ids if ObjectId.is_valid(value)]
        companies_by_id = (
            {
                company.id: company.name
                for company in await self.companies.find_many(
                    {"_id": {"$in": valid_company_ids}}, limit=len(valid_company_ids)
                )
            }
            if valid_company_ids
            else {}
        )

        company_counts: dict[str, dict[str, int]] = {}
        company_identity: dict[str, tuple[str | None, str]] = {}
        for application in applications:
            drive = drive_by_id.get(application.drive_id)
            company_id = str(drive.company_id) if drive else None
            company_name = (
                companies_by_id.get(company_id, "Unknown company")
                if company_id
                else "Unknown company"
            )
            key = company_id or f"unknown:{company_name}"
            company_identity.setdefault(key, (company_id, company_name))
            row = company_counts.setdefault(
                key,
                {"applied": 0, "shortlisted": 0, "rejected": 0},
            )
            status = _status_value(application.status)
            if status in row:
                row[status] += 1

        company_rows = [
            TpoCompanyApplicationCounts(
                company_id=company_identity[key][0],
                company_name=company_identity[key][1],
                applied=counts["applied"],
                shortlisted=counts["shortlisted"],
                rejected=counts["rejected"],
                total=sum(counts.values()),
            )
            for key, counts in company_counts.items()
        ]
        if company_sort == "shortlisted":
            company_rows.sort(
                key=lambda row: (-row.shortlisted, -row.total, row.company_name.lower())
            )
        elif company_sort == "name":
            company_rows.sort(key=lambda row: row.company_name.lower())
        else:
            company_rows.sort(
                key=lambda row: (-row.total, -row.shortlisted, row.company_name.lower())
            )

        # Per-drive comparison uses only drives that actually received an
        # application in this filtered view; no zero-only drives are invented.
        drive_counts: dict[str, dict[str, int]] = {}
        for application in applications:
            drive = drive_by_id.get(application.drive_id)
            if not drive:
                continue
            row = drive_counts.setdefault(
                drive.id,
                {"applied": 0, "shortlisted": 0, "rejected": 0},
            )
            status = _status_value(application.status)
            if status in row:
                row[status] += 1

        drive_rows = []
        for drive_id, counts in drive_counts.items():
            drive = drive_by_id[drive_id]
            company_id = str(drive.company_id) if drive.company_id else None
            drive_rows.append(
                TpoDriveApplicationCounts(
                    drive_id=drive_id,
                    job_title=drive.job_title,
                    company_id=company_id,
                    company_name=companies_by_id.get(company_id, "Unknown company")
                    if company_id
                    else "Unknown company",
                    drive_status=_status_value(drive.status),
                    applied=counts["applied"],
                    shortlisted=counts["shortlisted"],
                    rejected=counts["rejected"],
                    total=sum(counts.values()),
                )
            )
        drive_rows.sort(key=lambda row: (-row.total, -row.shortlisted, row.job_title.lower()))

        # Aggregate domain radar for the drives/applicants in this view. Only
        # real graded answers contribute; an empty list means no evidence.
        view_drive_ids = {application.drive_id for application in applications}
        domain_attempts = []
        for drive in drives:
            if drive.id not in view_drive_ids or not drive.required_assessment_id:
                continue
            drive_applicant_ids = {
                application.student_id
                for application in applications
                if application.drive_id == drive.id
            }
            if not drive_applicant_ids:
                continue
            domain_attempts.extend(
                await self.attempts.find_many(
                    {
                        "assessment_id": str(drive.required_assessment_id),
                        "student_id": {"$in": list(drive_applicant_ids)},
                    },
                    limit=_ANALYTICS_FETCH_LIMIT,
                )
            )
        domain_scores = await self._domain_scores_for_attempts(domain_attempts)

        return TpoApplicationAnalyticsResponse(
            total_applications=len(applications),
            total_drives=len(drives),
            date_from=date_from,
            date_to=date_to,
            status_breakdown=breakdown,
            unique_applicants=len(applicant_student_ids),
            students_with_applications=len(applicant_student_ids),
            total_students=len(applicant_student_ids),
            active_drives=active_drives,
            legacy_selected=legacy_selected,
            domain_scores=domain_scores,
            synthetic_application_count=sum(1 for application in applications if application.is_synthetic),
            applied_rate_pct=_rate_pct(breakdown.applied, len(applications)),
            shortlisting_rate_pct=_rate_pct(breakdown.shortlisted, len(applications)),
            rejection_rate_pct=_rate_pct(breakdown.rejected, len(applications)),
            departments=departments,
            monthly_trend=monthly_trend,
            companies=company_rows[:top_n],
            company_count=len(company_rows),
            company_sort=company_sort,
            top_n=top_n,
            drives=drive_rows,
            drive_count=len(drive_rows),
        )

    async def get_tpo_application_records(
        self,
        tpo_user_id: str,
        *,
        status: str | None,
        company_id: str | None,
        department: str | None,
        drive_id: str | None,
        date_from: date | None,
        date_to: date | None,
        page: int,
        limit: int,
    ) -> TpoApplicationRecordsResponse:
        """Paginated application rows behind a TPO's own analytics charts.

        This powers the dashboard drill-down: clicking a status slice, a
        company bar, a department bar or a drive bar lists exactly the
        applications that produced that number. Every filter is applied to
        the same population the charts use, and ownership is enforced by
        restricting to drives created by this TPO. Private student data
        (contact details, resumes, answers) is never included.
        """
        if date_from and date_to and date_from > date_to:
            raise AnalyticsError("date_from must be on or before date_to.", 400)

        empty = TpoApplicationRecordsResponse(total=0, page=page, limit=limit, entries=[])

        tpo = await self.tpos.get_by_user_id(tpo_user_id)
        if not tpo:
            return empty

        drives = await self.drives.find_many({"created_by": tpo.id}, limit=_ANALYTICS_FETCH_LIMIT)
        if not drives:
            return empty
        drive_by_id = {drive.id: drive for drive in drives}

        if drive_id:
            if drive_id not in drive_by_id:
                raise AnalyticsError("Drive not found.", 404)
            drive_ids = [drive_id]
        else:
            drive_ids = list(drive_by_id)

        query: dict = {"drive_id": {"$in": drive_ids}}
        if status:
            query["status"] = status
        if date_from or date_to:
            applied_range: dict = {}
            if date_from:
                applied_range["$gte"] = datetime.combine(date_from, time.min)
            if date_to:
                applied_range["$lte"] = datetime.combine(date_to, time.max)
            query["applied_at"] = applied_range

        applications = await self.applications.find_many(query, limit=_ANALYTICS_FETCH_LIMIT)

        # One batched student lookup for name + department, then one batched
        # company lookup for the drive's company name.
        student_ids = {application.student_id for application in applications}
        valid_student_ids = [ObjectId(value) for value in student_ids if ObjectId.is_valid(value)]
        students = (
            {
                student.id: student
                for student in await self.students.find_many(
                    {"_id": {"$in": valid_student_ids}}, limit=len(valid_student_ids)
                )
            }
            if valid_student_ids
            else {}
        )

        company_ids = {
            str(drive.company_id)
            for drive in drives
            if drive.company_id and (not company_id or str(drive.company_id) == company_id)
        }
        companies = (
            {
                company.id: company.name
                for company in await self.companies.find_many(
                    {"_id": {"$in": [ObjectId(cid) for cid in company_ids if ObjectId.is_valid(cid)]}},
                    limit=len(company_ids),
                )
            }
            if company_ids
            else {}
        )

        rows: list[TpoApplicationRecordEntry] = []
        for application in applications:
            drive = drive_by_id.get(application.drive_id)
            if not drive:
                continue
            cid = str(drive.company_id) if drive.company_id else None
            if company_id and cid != company_id:
                continue
            student = students.get(application.student_id)
            row_department = _normalize_department(student.department if student else None)
            if department and row_department != department:
                continue
            rows.append(
                TpoApplicationRecordEntry(
                    application_id=application.id,
                    student_id=application.student_id,
                    student_name=student.name if student else "Unknown student",
                    department=_normalize_department(student.department) if student else None,
                    drive_id=drive.id,
                    job_title=drive.job_title,
                    company_id=cid,
                    company_name=companies.get(cid, "Unknown company") if cid else "Unknown company",
                    status=_status_value(application.status),
                    applied_at=application.applied_at,
                    is_synthetic=application.is_synthetic,
                )
            )

        rows.sort(key=lambda row: (row.applied_at, row.application_id), reverse=True)
        total = len(rows)
        start = (page - 1) * limit
        return TpoApplicationRecordsResponse(
            total=total,
            page=page,
            limit=limit,
            entries=rows[start : start + limit],
        )

    # ------------------------------------------------------------------
    # Per-drive detail (Phase: per-drive rankings & participation).
    #
    # Rankings moved out of the main analytics response into drive-scoped
    # endpoints so each drive's expanded breakdown shows its own ranking,
    # applicants and participants without duplicating data.
    # ------------------------------------------------------------------

    async def _get_owned_drive(
        self, tpo_user_id: str, drive_id: str, *, actor_role: str = "tpo"
    ) -> PlacementDriveInDB:
        """The drive being inspected must exist AND be readable by the actor.

        Admins oversee every drive; a TPO may only inspect its own (404 hides
        other TPOs' drives from probing, 403 covers the impossible-id case).
        """
        drive = await self.drives.get_by_id(drive_id)
        if not drive:
            raise AnalyticsError("Drive not found.", 404)
        if actor_role == "admin":
            return drive
        tpo = await self.tpos.get_by_user_id(tpo_user_id)
        if not tpo:
            raise AnalyticsError("Drive not found.", 404)
        if drive.created_by != tpo.id:
            raise AnalyticsError("You do not have permission to view this drive's analytics.", 403)
        return drive

    async def _drive_attempt_pool(self, drive: PlacementDriveInDB, applicant_ids: set[str]) -> list:
        """All attempts on the drive's required assessment, restricted to the
        drive's own applicants.

        Restricting to the applicant set is what makes this drive-exact: a
        drive assessment can only be started through an application (see
        assessment_service.start_attempt), so in the normal case — one drive
        per assessment — every attempter is already an applicant and this
        restriction changes nothing. But two drives MAY reference the same
        assessment, and then the assessment_id alone cannot tell which drive
        an attempt belongs to; the applicant set can. Without it, drive A's
        leaderboard would list students who only ever applied to drive B.
        """
        if not drive.required_assessment_id:
            return []
        return await self.attempts.find_many(
            {"assessment_id": str(drive.required_assessment_id), "student_id": {"$in": list(applicant_ids)}},
            limit=_ANALYTICS_FETCH_LIMIT,
        )

    async def get_drive_ranking(
        self, tpo_user_id: str, drive_id: str, *, actor_role: str = "tpo"
    ) -> DriveAssessmentRanking:
        drive = await self._get_owned_drive(tpo_user_id, drive_id, actor_role=actor_role)
        company = await self.companies.get_by_id(str(drive.company_id))
        company_name = company.name if company else "Unknown company"

        assessment = (
            await self.assessments.get_by_id(str(drive.required_assessment_id))
            if drive.required_assessment_id
            else None
        )
        if not assessment:
            raise AnalyticsError("This drive has no required assessment, so there is nothing to rank.", 404)

        applications = await self.applications.find_many({"drive_id": drive.id}, limit=_ANALYTICS_FETCH_LIMIT)
        applicant_ids = {app.student_id for app in applications}
        attempts = await self._drive_attempt_pool(drive, applicant_ids)

        # Best score per student (a student can retake a drive assessment —
        # their best submitted attempt represents them in the ranking).
        # Unranked by design: in-progress attempts have no final score.
        best_by_student: dict[str, tuple[float, object]] = {}
        for attempt in attempts:
            if attempt.status != AttemptStatus.SUBMITTED:
                continue
            score = _attempt_score_pct(attempt)
            existing = best_by_student.get(attempt.student_id)
            if existing is None or score > existing[0]:
                best_by_student[attempt.student_id] = (score, attempt)

        # Same ordering the old standalone ranking used (score descending);
        # ties now break deterministically by earlier submission, then
        # student id, instead of by dict insertion order.
        ordered = sorted(
            best_by_student.items(),
            key=lambda kv: (
                -kv[1][0],
                kv[1][1].submitted_at or kv[1][1].started_at,
                kv[0],
            ),
        )

        student_ids = [student_id for student_id, _ in ordered]
        students = {
            student.id: student
            for student in await self.students.find_many(
                {"_id": {"$in": [ObjectId(sid) for sid in student_ids]}}, limit=_SEARCH_STUDENT_CAP
            )
        }

        entries: list[DriveAssessmentRankingEntry] = []
        for rank, (student_id, (score, attempt)) in enumerate(ordered, start=1):
            student = students.get(student_id)
            entries.append(
                DriveAssessmentRankingEntry(
                    rank=rank,
                    student_id=student_id,
                    student_name=student.name if student else "Unknown student",
                    department=_normalize_department(student.department) if student else None,
                    cgpa=student.cgpa if student else None,
                    score_pct=score,
                    submitted_at=attempt.submitted_at or attempt.started_at,
                    is_synthetic=bool(student and student.is_synthetic),
                )
            )

        return DriveAssessmentRanking(
            drive_id=drive.id,
            job_title=drive.job_title,
            company_name=company_name,
            assessment_id=assessment.id,
            assessment_title=assessment.title,
            entries=entries,
        )

    async def get_drive_applicants(
        self,
        tpo_user_id: str,
        drive_id: str,
        page: int,
        limit: int,
        search: str | None,
    ) -> DriveApplicantsResponse:
        drive = await self._get_owned_drive(tpo_user_id, drive_id)
        company = await self.companies.get_by_id(str(drive.company_id))
        company_name = company.name if company else "Unknown company"

        query: dict = {"drive_id": drive.id}
        if search:
            # Name search resolves against the students collection first, then
            # narrows the application query — no name-based joins anywhere.
            matching = await self.students.find_many(
                {"name": _name_search_regex(search)}, limit=_SEARCH_STUDENT_CAP
            )
            query["student_id"] = {"$in": [student.id for student in matching]}

        total = await self.applications.count(query)
        applications = await self.applications.find_many(
            query, page=page, limit=limit, sort=[("applied_at", -1)]
        )

        # One batched student lookup for the page (no per-row queries).
        page_student_ids = [app.student_id for app in applications]
        students = {
            student.id: student
            for student in await self.students.find_many(
                {"_id": {"$in": [ObjectId(sid) for sid in page_student_ids]}}, limit=limit
            )
        }

        # Defensive dedupe by student (one application per drive/student is
        # enforced at creation; legacy duplicates must not show twice).
        seen_student_ids: set[str] = set()
        entries: list[DriveApplicantEntry] = []
        for app in applications:
            if app.student_id in seen_student_ids:
                continue
            seen_student_ids.add(app.student_id)
            student = students.get(app.student_id)
            status = app.status.value if hasattr(app.status, "value") else app.status
            entries.append(
                DriveApplicantEntry(
                    application_id=app.id,
                    student_id=app.student_id,
                    student_name=student.name if student else "Unknown student",
                    department=_normalize_department(student.department) if student else None,
                    batch_year=student.batch_year if student else None,
                    status=status,
                    applied_at=app.applied_at,
                    is_synthetic=app.is_synthetic,
                )
            )

        return DriveApplicantsResponse(
            drive_id=drive.id,
            job_title=drive.job_title,
            company_name=company_name,
            total=total,
            page=page,
            limit=limit,
            entries=entries,
        )

    async def get_drive_participants(
        self,
        tpo_user_id: str,
        drive_id: str,
        page: int,
        limit: int,
        search: str | None,
    ) -> DriveParticipantsResponse:
        drive = await self._get_owned_drive(tpo_user_id, drive_id)
        company = await self.companies.get_by_id(str(drive.company_id))
        company_name = company.name if company else "Unknown company"

        assessment = (
            await self.assessments.get_by_id(str(drive.required_assessment_id))
            if drive.required_assessment_id
            else None
        )
        if not assessment:
            return DriveParticipantsResponse(
                drive_id=drive.id,
                job_title=drive.job_title,
                company_name=company_name,
                assessment_id=None,
                assessment_title=None,
                total=0,
                page=page,
                limit=limit,
                entries=[],
            )

        applications = await self.applications.find_many({"drive_id": drive.id}, limit=_ANALYTICS_FETCH_LIMIT)
        applicant_ids = {app.student_id for app in applications}
        attempts = await self._drive_attempt_pool(drive, applicant_ids)

        # One row per student: their best submitted attempt represents them
        # (same selection the ranking uses); a student who started but never
        # submitted is shown with their latest in-progress attempt and no
        # score — an actual attempt, not just an assignment.
        best_by_student: dict[str, tuple[float, object]] = {}
        in_progress_by_student: dict[str, object] = {}
        for attempt in attempts:
            if attempt.status == AttemptStatus.SUBMITTED:
                score = _attempt_score_pct(attempt)
                existing = best_by_student.get(attempt.student_id)
                if existing is None or score > existing[0]:
                    best_by_student[attempt.student_id] = (score, attempt)
            else:
                current = in_progress_by_student.get(attempt.student_id)
                if current is None or (attempt.started_at or "") > (current.started_at or ""):
                    in_progress_by_student[attempt.student_id] = attempt

        participant_ids = set(best_by_student) | set(in_progress_by_student)
        participant_rows: list[tuple[str, object]] = [
            (student_id, best_by_student[student_id][1] if student_id in best_by_student
             else in_progress_by_student[student_id])
            for student_id in participant_ids
        ]

        if search:
            matching = await self.students.find_many(
                {"name": _name_search_regex(search)}, limit=_SEARCH_STUDENT_CAP
            )
            allowed_ids = {student.id for student in matching}
            participant_rows = [row for row in participant_rows if row[0] in allowed_ids]

        # Fetch all names once, then sort + paginate in memory (the pool is
        # deduped per student, so it is bounded by the applicant count).
        pool_student_ids = [student_id for student_id, _ in participant_rows]
        students = {
            student.id: student
            for student in await self.students.find_many(
                {"_id": {"$in": [ObjectId(sid) for sid in pool_student_ids]}}, limit=_SEARCH_STUDENT_CAP
            )
        }

        def _sort_key(row: tuple[str, object]):
            student = students.get(row[0])
            return (student.name if student else "", row[0])

        participant_rows.sort(key=_sort_key)
        total = len(participant_rows)
        start = (page - 1) * limit
        page_rows = participant_rows[start:start + limit]

        entries: list[DriveParticipantEntry] = []
        for student_id, attempt in page_rows:
            student = students.get(student_id)
            submitted = attempt.status == AttemptStatus.SUBMITTED
            entries.append(
                DriveParticipantEntry(
                    student_id=student_id,
                    student_name=student.name if student else "Unknown student",
                    department=_normalize_department(student.department) if student else None,
                    batch_year=student.batch_year if student else None,
                    attempt_id=attempt.id,
                    attempt_status=attempt.status.value if hasattr(attempt.status, "value") else attempt.status,
                    score_pct=_attempt_score_pct(attempt) if submitted else None,
                    started_at=attempt.started_at,
                    submitted_at=attempt.submitted_at,
                    is_synthetic=bool(student and student.is_synthetic),
                )
            )

        return DriveParticipantsResponse(
            drive_id=drive.id,
            job_title=drive.job_title,
            company_name=company_name,
            assessment_id=assessment.id,
            assessment_title=assessment.title,
            total=total,
            page=page,
            limit=limit,
            entries=entries,
        )

    async def get_admin_analytics(self) -> AdminAnalyticsResponse:
        total_students = await self.students.count({})
        total_tpos = await self.tpos.count({})
        total_drives = await self.drives.count({})
        open_drives = await self.drives.count({"status": "open"})
        closed_drives = total_drives - open_drives

        # All admin aggregates are now computed by the database itself, so the
        # numbers stay exact regardless of the bounded document fetches used by
        # the list endpoints. Previously some fields used count() while others
        # used the first 5,000 rows, silently mixing real totals with lower
        # bounds in the same response.
        status_counts = await self.applications.status_counts()
        # Legacy selected rows are counted as shortlisted so the three current
        # statuses always reconcile with the total. No document is modified.
        legacy_selected = status_counts.get("selected", 0)
        breakdown = ApplicationStatusBreakdown(
            applied=status_counts.get("applied", 0),
            shortlisted=status_counts.get("shortlisted", 0) + legacy_selected,
            rejected=status_counts.get("rejected", 0),
            selected=0,
        )
        total_applications = breakdown.applied + breakdown.shortlisted + breakdown.rejected
        unique_applicants = len(await self.applications.distinct_students())
        placed_student_ids = await self.applications.distinct_students_by_status("selected")
        placement_rate = round(100 * len(placed_student_ids) / total_students, 1) if total_students else 0.0
        total_companies = await self.companies.count({})

        total_categories = await self.categories.count({})
        total_questions = await self.questions.count({})
        total_assessments = await self.assessments.count({})

        total_attempts = await self.attempts.count({})
        submitted_attempts, average_score_raw = await self.attempts.submitted_score_stats(
            easy_marks=DIFFICULTY_MARKS[DifficultyLevel.EASY],
            medium_marks=DIFFICULTY_MARKS[DifficultyLevel.MEDIUM],
            hard_marks=DIFFICULTY_MARKS[DifficultyLevel.HARD],
        )
        # Preserve "no scored attempts" as None: a 0.0 here would look like a
        # genuine average of zero marks.
        average_score = (
            round(average_score_raw, 1) if average_score_raw is not None else None
        )

        skill_overview = sorted(
            (
                SkillMasteryOverview(
                    skill_tag=row["skill_tag"],
                    avg_mastery_pct=round(row["avg_mastery_pct"], 1),
                    student_count=row["student_count"],
                )
                for row in await self.knowledge_states.mastery_overview()
            ),
            key=lambda s: (-s.avg_mastery_pct, s.skill_tag),
        )

        # User-account distribution is counted from the auth collection, not
        # inferred from profile documents. Departments are canonicalised so
        # "CS" and "Computer Science" count as one department; unknown free
        # text is preserved and blank values get one explicit bucket.
        role_counts = {
            role: await self.users.count({"role": role})
            for role in ("student", "tpo", "admin")
        }
        student_docs = await self.students.find_many({}, limit=_ANALYTICS_FETCH_LIMIT)
        department_counts: dict[str, int] = {}
        for student in student_docs:
            department = _normalize_department(student.department)
            department_counts[department] = department_counts.get(department, 0) + 1
        department_student_counts = [
            AdminDepartmentStudentCount(department=department, count=count)
            for department, count in sorted(
                department_counts.items(), key=lambda item: (-item[1], item[0].lower())
            )
        ]

        # Provenance disclosure: how much of the overview is demo seed data.
        synthetic_students = await self.students.count({"is_synthetic": True})
        synthetic_applications = await self.applications.count({"is_synthetic": True})

        return AdminAnalyticsResponse(
            total_students=total_students,
            total_tpos=total_tpos,
            total_drives=total_drives,
            open_drives=open_drives,
            closed_drives=closed_drives,
            total_applications=total_applications,
            unique_applicants=unique_applicants,
            students_with_applications=unique_applicants,
            total_companies=total_companies,
            legacy_selected=legacy_selected,
            application_breakdown=breakdown,
            placed_students=len(placed_student_ids),
            placement_rate_pct=placement_rate,
            total_categories=total_categories,
            total_questions=total_questions,
            total_assessments=total_assessments,
            total_attempts=total_attempts,
            submitted_attempts=submitted_attempts,
            average_score_pct=average_score,
            skill_mastery_overview=skill_overview,
            total_admins=role_counts["admin"],
            user_role_counts=[
                AdminUserRoleCount(role=role, count=role_counts[role])
                for role in ("student", "tpo", "admin")
            ],
            department_student_counts=department_student_counts,
            synthetic_students=synthetic_students,
            synthetic_applications=synthetic_applications,
        )

    async def get_admin_applications(
        self,
        *,
        status: str | None,
        company_id: str | None,
        drive_id: str | None,
        department: str | None,
        assessment_completion: str | None,
        date_from: date | None,
        date_to: date | None,
        page: int,
        limit: int,
    ) -> AdminApplicationRecordsResponse:
        """Cross-drive application workspace for admins.

        Every filter is applied to the same population, statuses are the three
        current ones (legacy ``selected`` mapped to ``shortlisted``), and the
        summary cards are computed before the status filter so all four cards
        stay meaningful while one is active.
        """
        if date_from and date_to and date_from > date_to:
            raise AnalyticsError("date_from must be on or before date_to.", 400)

        empty = AdminApplicationRecordsResponse(
            total=0,
            page=page,
            limit=limit,
            summary=AdminApplicationSummary(),
            entries=[],
        )

        drives = await self.drives.find_many({}, limit=_ANALYTICS_FETCH_LIMIT)
        drive_by_id = {drive.id: drive for drive in drives}

        if drive_id and drive_id not in drive_by_id:
            raise AnalyticsError("Drive not found.", 404)

        query: dict = {}
        if drive_id:
            query["drive_id"] = drive_id
        if date_from or date_to:
            applied_range: dict = {}
            if date_from:
                applied_range["$gte"] = datetime.combine(date_from, time.min)
            if date_to:
                applied_range["$lte"] = datetime.combine(date_to, time.max)
            query["applied_at"] = applied_range

        applications = await self.applications.find_many(query, limit=_ANALYTICS_FETCH_LIMIT)

        # Company filter narrows by the drive's company.
        if company_id:
            allowed_drive_ids = {
                drive.id
                for drive in drives
                if drive.company_id and str(drive.company_id) == company_id
            }
            applications = [
                application
                for application in applications
                if application.drive_id in allowed_drive_ids
            ]

        # Batched lookups for the fields the table needs.
        student_ids = {application.student_id for application in applications}
        valid_student_ids = [ObjectId(value) for value in student_ids if ObjectId.is_valid(value)]
        students = (
            {
                student.id: student
                for student in await self.students.find_many(
                    {"_id": {"$in": valid_student_ids}}, limit=len(valid_student_ids)
                )
            }
            if valid_student_ids
            else {}
        )

        company_ids = {
            str(drive.company_id) for drive in drives if drive.company_id
        }
        valid_company_ids = [ObjectId(value) for value in company_ids if ObjectId.is_valid(value)]
        companies = (
            {
                company.id: company.name
                for company in await self.companies.find_many(
                    {"_id": {"$in": valid_company_ids}}, limit=len(valid_company_ids)
                )
            }
            if valid_company_ids
            else {}
        )

        assessment_ids = {
            str(drive.required_assessment_id)
            for drive in drives
            if drive.required_assessment_id
        }
        valid_assessment_ids = [
            ObjectId(value) for value in assessment_ids if ObjectId.is_valid(value)
        ]
        assessments = (
            {
                assessment.id: assessment
                for assessment in await self.assessments.find_many(
                    {"_id": {"$in": valid_assessment_ids}}, limit=len(valid_assessment_ids)
                )
            }
            if valid_assessment_ids
            else {}
        )

        # Rank cache: ranks are computed against EVERY application to a drive,
        # not just the filtered view, so filtering never changes a rank.
        rank_cache: dict[str, dict[str, tuple[int, float]]] = {}

        async def rank_info_for(drive) -> dict[str, tuple[int, float]]:
            if drive.id in rank_cache:
                return rank_cache[drive.id]
            if not drive.required_assessment_id:
                rank_cache[drive.id] = {}
                return {}
            all_applications = await self.applications.find_many(
                {"drive_id": drive.id}, limit=_ANALYTICS_FETCH_LIMIT
            )
            applicant_ids = {application.student_id for application in all_applications}
            attempts = await self._drive_attempt_pool(drive, applicant_ids)
            best_by_student: dict[str, float] = {}
            for attempt in attempts:
                if attempt.status != AttemptStatus.SUBMITTED:
                    continue
                score = _attempt_score_pct(attempt)
                if attempt.student_id not in best_by_student or score > best_by_student[attempt.student_id]:
                    best_by_student[attempt.student_id] = score
            ordered = sorted(best_by_student.items(), key=lambda item: (-item[1], item[0]))
            result = {
                student_id: (rank, score)
                for rank, (student_id, score) in enumerate(ordered, start=1)
            }
            rank_cache[drive.id] = result
            return result

        rows: list[AdminApplicationEntry] = []
        for application in applications:
            drive = drive_by_id.get(application.drive_id)
            if not drive:
                continue
            student = students.get(application.student_id)
            row_department = _normalize_department(student.department) if student else None
            if department and row_department != _normalize_department(department):
                continue

            assessment_status = _status_value(application.assessment_status)
            if assessment_completion == "completed" and assessment_status not in ("passed", "failed"):
                continue
            if assessment_completion == "pending" and assessment_status not in ("pending", "expired"):
                continue
            if assessment_completion == "not_required" and assessment_status != "not_required":
                continue

            company_key = str(drive.company_id) if drive.company_id else None
            assessment = (
                assessments.get(str(drive.required_assessment_id))
                if drive.required_assessment_id
                else None
            )
            rank = None
            best_score = None
            if drive.required_assessment_id:
                rank_map = await rank_info_for(drive)
                if application.student_id in rank_map:
                    rank, best_score = rank_map[application.student_id]

            rows.append(
                AdminApplicationEntry(
                    application_id=application.id,
                    student_id=application.student_id,
                    student_name=student.name if student else "Unknown student",
                    department=row_department,
                    company_id=company_key,
                    company_name=companies.get(company_key, "Unknown company")
                    if company_key
                    else "Unknown company",
                    drive_id=drive.id,
                    job_title=drive.job_title,
                    assessment_id=str(drive.required_assessment_id)
                    if drive.required_assessment_id
                    else None,
                    assessment_title=assessment.title if assessment else None,
                    assessment_status=assessment_status,
                    assessment_score_pct=(
                        application.assessment_score_pct
                        if application.assessment_score_pct is not None
                        else best_score
                    ),
                    rank=rank,
                    status=_effective_status(application.status),
                    applied_at=application.applied_at,
                    is_synthetic=application.is_synthetic,
                )
            )

        # Summary reflects every filter except status.
        summary = AdminApplicationSummary(
            total=len(rows),
            applied=sum(1 for row in rows if row.status == "applied"),
            shortlisted=sum(1 for row in rows if row.status == "shortlisted"),
            rejected=sum(1 for row in rows if row.status == "rejected"),
            legacy_selected=_legacy_selected_count(applications),
        )

        if status:
            rows = [row for row in rows if row.status == status]

        rows.sort(key=lambda row: (row.applied_at, row.application_id), reverse=True)
        total = len(rows)
        start = (page - 1) * limit
        return AdminApplicationRecordsResponse(
            total=total,
            page=page,
            limit=limit,
            summary=summary,
            entries=rows[start : start + limit],
        )

    async def get_admin_application_filters(self) -> AdminApplicationFiltersResponse:
        """Live filter options for the admin applications workspace."""
        companies = await self.companies.find_many({}, limit=_ANALYTICS_FETCH_LIMIT)
        drives = await self.drives.find_many(
            {}, limit=_ANALYTICS_FETCH_LIMIT, sort=[("created_at", -1)]
        )
        students = await self.students.find_many({}, limit=_ANALYTICS_FETCH_LIMIT)

        company_names = {company.id: company.name for company in companies}
        company_options = sorted(
            (
                AdminApplicationFilterCompany(id=company.id, name=company.name)
                for company in companies
            ),
            key=lambda item: item.name.lower(),
        )
        drive_options = [
            AdminApplicationFilterDrive(
                id=drive.id,
                job_title=drive.job_title,
                company_name=company_names.get(str(drive.company_id), "Unknown company"),
                status=_status_value(drive.status),
            )
            for drive in drives
        ]
        departments = sorted(
            {_normalize_department(student.department) for student in students},
            key=str.lower,
        )

        return AdminApplicationFiltersResponse(
            companies=company_options,
            drives=drive_options,
            departments=departments,
        )

    async def get_admin_activity(self) -> AdminActivityResponse:
        """Monthly platform activity for the admin overview.

        Uses the domain timestamps that actually exist — new user accounts
        (``users.created_at``), new drives (``placement_drives.created_at``)
        and applications (``applications.applied_at``). The incomplete
        ``activity_logs`` collection is deliberately not used.
        """
        role_counts = {
            role: await self.users.count({"role": role})
            for role in ("student", "tpo", "admin")
        }
        total_users = await self.users.count({})

        users = await self.users.find_many({}, limit=_ANALYTICS_FETCH_LIMIT)
        drives = await self.drives.find_many({}, limit=_ANALYTICS_FETCH_LIMIT)
        applications = await self.applications.find_many({}, limit=_ANALYTICS_FETCH_LIMIT)
        students = await self.students.find_many({}, limit=_ANALYTICS_FETCH_LIMIT)

        department_counts: dict[str, int] = {}
        for student in students:
            department = _normalize_department(student.department)
            department_counts[department] = department_counts.get(department, 0) + 1
        department_student_counts = [
            AdminDepartmentStudentCount(department=department, count=count)
            for department, count in sorted(
                department_counts.items(), key=lambda item: (-item[1], item[0].lower())
            )
        ]

        monthly: dict[str, dict[str, int]] = {}

        def bucket(key: str) -> dict[str, int]:
            return monthly.setdefault(
                key, {"new_students": 0, "new_drives": 0, "applications": 0}
            )

        for user in users:
            # "New students" means student accounts only; TPO/admin signups
            # are represented in the user-distribution chart, not this line.
            created_at = _recorded_at(user)
            if created_at is not None and _status_value(user.role) == "student":
                bucket(_month_key(created_at))["new_students"] += 1
        for drive in drives:
            created_at = _recorded_at(drive)
            if created_at is not None:
                bucket(_month_key(created_at))["new_drives"] += 1
        for application in applications:
            applied_at = _recorded_at(application, "applied_at")
            if applied_at is not None:
                bucket(_month_key(applied_at))["applications"] += 1

        if monthly:
            month_keys = sorted(monthly)
            full_months = _clamped_month_keys(
                _month_start(month_keys[0]),
                _month_start(month_keys[-1]),
            )
        else:
            full_months = []

        monthly_activity = [
            AdminActivityMonthPoint(
                month=key,
                new_students=monthly.get(key, {}).get("new_students", 0),
                new_drives=monthly.get(key, {}).get("new_drives", 0),
                applications=monthly.get(key, {}).get("applications", 0),
            )
            for key in full_months
        ]

        return AdminActivityResponse(
            user_distribution=[
                AdminUserRoleCount(role=role, count=role_counts[role])
                for role in ("student", "tpo", "admin")
            ],
            total_users=total_users,
            department_student_counts=department_student_counts,
            monthly_activity=monthly_activity,
        )
