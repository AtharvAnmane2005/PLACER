"""
Knowledge Tracing System models.

Grading rules (see PROJECT_PROGRESS.md for the full reasoning):

- MCQ is exact-match against ``correct_answer``.
- Coding questions are executed against one or more stdin/stdout test cases
  by ``code_execution_service``. A question passes only when every test case
  passes. Questions created before test cases existed fall back to a single
  empty-input case compared against ``correct_answer``, preserving the old
  behaviour.
- Descriptive questions are stored but not auto-graded — they're flagged for
  manual review.

The local code runner is a best-effort subprocess executor, NOT a hardened
sandbox — see ``code_execution_service`` for the security caveats.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.base import MongoBaseModel, PyObjectId


class AssessmentType(str, Enum):
    PRACTICE = "practice"
    DRIVE = "drive"


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


DIFFICULTY_ORDER = [DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD]
DIFFICULTY_MARKS = {DifficultyLevel.EASY: 1, DifficultyLevel.MEDIUM: 3, DifficultyLevel.HARD: 5}


class QuestionType(str, Enum):
    MCQ = "mcq"
    MULTIPLE_SELECT = "multiple_select"
    TRUE_FALSE = "true_false"
    CODING = "coding"
    DESCRIPTIVE = "descriptive"


class QuestionStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class AssessmentFormat(str, Enum):
    """Adaptive (legacy engine) vs fixed-set standardized assessments."""

    ADAPTIVE = "adaptive"
    STANDARDIZED = "standardized"


class AssessmentPublishStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


# Exactly five equal sections / six-ten-four difficulty mix for every
# standardized placement-drive assessment. These are assessment *rules*,
# not question content — no questions are fabricated from them.
PLACEMENT_SECTIONS: tuple[str, ...] = (
    "Quantitative Aptitude",
    "Logical Reasoning",
    "Verbal Ability",
    "Technical Knowledge",
    "Programming / Problem Solving",
)
PLACEMENT_SECTION_SIZE = 4
PLACEMENT_TOTAL_QUESTIONS = 20
# Preferred number of coding questions in the Programming section of a
# standardized drive assessment. The selector fills the hardest planned slots
# first and falls back to an objective question when the bank has no coding
# question for a slot, so generation never fails just because a bank has no
# coding content.
PLACEMENT_CODING_QUESTIONS = 1
PLACEMENT_DIFFICULTY_QUOTA = {
    DifficultyLevel.EASY: 6,
    DifficultyLevel.MEDIUM: 10,
    DifficultyLevel.HARD: 4,
}
OBJECTIVE_QUESTION_TYPES = (QuestionType.MCQ, QuestionType.MULTIPLE_SELECT, QuestionType.TRUE_FALSE)


class CodingLanguage(str, Enum):
    """Languages the local code runner can execute.

    Kept deliberately small: Python and JavaScript are the two runtimes
    guaranteed to be present in this project's environments (the backend
    venv and the Node install used by the frontend). Adding a compiled
    language later is a matter of extending the command registry in
    ``code_execution_service`` — no model changes needed.
    """

    PYTHON = "python"
    JAVASCRIPT = "javascript"


class TestCase(BaseModel):
    """One stdin/stdout test case for a coding question.

    The student's program reads ``input`` from stdin and its stdout is
    compared against ``expected_output`` (line-ending and trailing-whitespace
    normalised). Hidden cases are still run, but their input/expected/actual
    values are never returned to the student — only pass/fail.
    """

    name: str | None = None
    input: str = ""
    expected_output: str
    is_hidden: bool = True


class AttemptStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"


# ---------------------------------------------------------------------------
# DB documents
# ---------------------------------------------------------------------------
class QuestionCategoryInDB(MongoBaseModel):
    name: str
    parent_category_id: PyObjectId | None = None


class QuestionInDB(MongoBaseModel):
    category_id: PyObjectId
    skill_tags: list[str] = Field(default_factory=list)
    difficulty: DifficultyLevel
    type: QuestionType
    text: str
    options: list[str] = Field(default_factory=list)  # MCQ only
    correct_answer: str | None = None  # MCQ: option text. Coding: legacy expected output. Descriptive: None (manual grading).
    # --- Coding-only fields (ignored for other question types) ---
    language: CodingLanguage | None = None
    starter_code: str | None = None  # shown pre-filled in the student editor
    test_cases: list[TestCase] = Field(default_factory=list)
    marks: int
    company_tags: list[str] = Field(default_factory=list)
    created_by: PyObjectId
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # --- Optional management metadata. Missing on legacy seeded questions;
    # services treat those as active with topic derived from skill_tags[0].
    topic: str | None = None
    skill: str | None = None
    explanation: str | None = None
    status: QuestionStatus = QuestionStatus.ACTIVE
    updated_at: datetime | None = None


class AssessmentInDB(MongoBaseModel):
    title: str
    category_ids: list[PyObjectId] = Field(default_factory=list)
    question_pool_size: int = 10
    time_limit_sec: int = 1800
    anti_cheat_config: dict = Field(default_factory=dict)  # populated by Phase 11
    type: AssessmentType = AssessmentType.PRACTICE  # practice or drive assessment
    drive_id: PyObjectId | None = None  # links assessment to a specific drive (set by TPO), required for DRIVE type
    created_by: PyObjectId
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # --- Standardized assessment configuration (optional; legacy assessments
    # keep the adaptive defaults and are completely unaffected).
    format: AssessmentFormat = AssessmentFormat.ADAPTIVE
    status: AssessmentPublishStatus = AssessmentPublishStatus.DRAFT
    question_ids: list[str] = Field(default_factory=list)  # fixed, ordered, immutable after publish
    sections: list[dict] = Field(default_factory=list)  # section metadata + per-section question IDs
    total_marks: int = 0
    passing_marks: int = 0
    negative_marks: float = 0.0
    instructions: str = ""
    allow_retake: bool = False
    randomize_options: bool = True
    template_id: str | None = None
    generated_at: datetime | None = None
    published_at: datetime | None = None


class AnsweredQuestion(BaseModel):
    question_id: str
    response: str
    is_correct: bool | None  # None for descriptive (ungraded)
    marks_awarded: float  # float to support fractional negative marking
    time_taken_sec: float | None = None
    difficulty_at_time: DifficultyLevel
    question_type: QuestionType | None = None  # stored for results, old records may omit it
    # Detailed per-test outcome for coding questions (None for other types).
    code_result: dict | None = None
    # --- Manual grading (descriptive questions only). ``graded_at`` stays
    # None until a TPO/admin reviewer scores the answer.
    graded_at: datetime | None = None
    graded_by: str | None = None
    feedback: str | None = None


class AssessmentAttemptInDB(MongoBaseModel):
    assessment_id: PyObjectId
    student_id: PyObjectId
    session_token: str
    asked_question_ids: list[str] = Field(default_factory=list)
    current_question_id: str | None = None
    current_difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    answers: list[AnsweredQuestion] = Field(default_factory=list)
    violations: list[dict] = Field(default_factory=list)  # populated by Phase 11
    status: AttemptStatus = AttemptStatus.IN_PROGRESS
    started_at: datetime = Field(default_factory=datetime.utcnow)
    submitted_at: datetime | None = None
    ip_address: str | None = None
    fingerprint_hash: str | None = None  # populated by Phase 11


class KnowledgeStateInDB(MongoBaseModel):
    student_id: PyObjectId
    skill_tag: str
    mastery_pct: float = 0.0
    confidence: float = 0.0
    attempts_count: int = 0
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    history: list[dict] = Field(default_factory=list)  # [{date, mastery_pct}]


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------
class CategoryCreateRequest(BaseModel):
    name: str
    parent_category_id: str | None = None


class CategoryResponse(BaseModel):
    id: str
    name: str
    parent_category_id: str | None


class QuestionCreateRequest(BaseModel):
    category_id: str
    skill_tags: list[str] = Field(default_factory=list)
    difficulty: DifficultyLevel
    type: QuestionType
    text: str
    options: list[str] = Field(default_factory=list)
    correct_answer: str | None = None
    language: CodingLanguage | None = None
    starter_code: str | None = None
    test_cases: list[TestCase] = Field(default_factory=list)
    company_tags: list[str] = Field(default_factory=list)
    topic: str | None = None
    skill: str | None = None
    explanation: str | None = None
    status: QuestionStatus = QuestionStatus.ACTIVE
    marks: int | None = Field(default=None, ge=0, le=100)


class QuestionUpdateRequest(BaseModel):
    category_id: str | None = None
    skill_tags: list[str] | None = None
    difficulty: DifficultyLevel | None = None
    type: QuestionType | None = None
    text: str | None = None
    options: list[str] | None = None
    correct_answer: str | None = None
    language: CodingLanguage | None = None
    starter_code: str | None = None
    test_cases: list[TestCase] | None = None
    company_tags: list[str] | None = None
    topic: str | None = None
    skill: str | None = None
    explanation: str | None = None
    status: QuestionStatus | None = None
    marks: int | None = Field(default=None, ge=0, le=100)


class QuestionAdminResponse(BaseModel):
    """Includes correct_answer — admin/TPO only, never sent to a student mid-assessment."""

    id: str
    category_id: str
    skill_tags: list[str]
    difficulty: DifficultyLevel
    type: QuestionType
    text: str
    options: list[str]
    correct_answer: str | None
    language: CodingLanguage | None = None
    starter_code: str | None = None
    test_cases: list[TestCase] = Field(default_factory=list)
    marks: int
    company_tags: list[str]
    topic: str | None = None
    skill: str | None = None
    explanation: str | None = None
    status: QuestionStatus = QuestionStatus.ACTIVE
    updated_at: datetime | None = None


class QuestionStudentView(BaseModel):
    """What a student sees during an assessment — no correct_answer field, ever."""

    id: str
    difficulty: DifficultyLevel
    type: QuestionType
    text: str
    options: list[str]
    marks: int
    # Coding-only. Only non-hidden test cases are exposed as samples.
    language: CodingLanguage | None = None
    starter_code: str | None = None
    visible_test_cases: list[TestCase] = Field(default_factory=list)


class AssessmentCreateRequest(BaseModel):
    title: str
    category_ids: list[str]
    question_pool_size: int = Field(default=10, ge=1, le=100)
    time_limit_sec: int = Field(default=1800, ge=60)
    max_violations: int = Field(default=3, ge=1, le=20)
    require_fullscreen: bool = True
    type: AssessmentType = AssessmentType.PRACTICE
    format: AssessmentFormat = AssessmentFormat.ADAPTIVE
    instructions: str = ""
    allow_retake: bool = False
    negative_marks: float = Field(default=0.0, ge=0.0, le=100.0)


class AssessmentResponse(BaseModel):
    id: str
    title: str
    category_ids: list[str]
    question_pool_size: int
    time_limit_sec: int
    anti_cheat_config: dict
    type: AssessmentType
    drive_id: str | None = None
    format: AssessmentFormat = AssessmentFormat.ADAPTIVE
    status: AssessmentPublishStatus = AssessmentPublishStatus.DRAFT
    question_count: int = 0
    total_marks: int = 0
    passing_marks: int = 0
    negative_marks: float = 0.0
    instructions: str = ""
    allow_retake: bool = False
    template_id: str | None = None
    sections: list[dict] = Field(default_factory=list)


class CodeTestCaseResult(BaseModel):
    """Outcome of one test case.

    ``input``/``expected_output``/``actual_output`` are only populated for
    non-hidden test cases — hidden cases reveal nothing but pass/fail.
    """

    index: int
    name: str | None = None
    is_hidden: bool = True
    passed: bool
    status: str  # passed | wrong_answer | runtime_error | timeout | output_limit_exceeded | skipped
    input: str | None = None
    expected_output: str | None = None
    actual_output: str | None = None
    stderr: str | None = None
    runtime_ms: float | None = None


class CodeRunSummary(BaseModel):
    passed: int
    total: int
    all_passed: bool
    status: str  # completed | disabled | unsupported_language | error
    results: list[CodeTestCaseResult] = Field(default_factory=list)
    error: str | None = None


class StartAttemptRequest(BaseModel):
    fingerprint_hash: str | None = None
    application_id: str | None = None  # required when starting a drive-linked assessment


class StartAttemptResponse(BaseModel):
    attempt_id: str
    session_token: str
    time_limit_sec: int
    time_remaining_sec: int
    anti_cheat_config: dict
    next_question: QuestionStudentView | None
    # Standardized attempts receive the full ordered, student-safe question
    # set up front so the UI can offer navigation. Adaptive attempts leave
    # these empty and keep using next_question.
    questions: list[QuestionStudentView] = Field(default_factory=list)
    answered_question_ids: list[str] = Field(default_factory=list)
    total_questions: int = 0
    format: AssessmentFormat = AssessmentFormat.ADAPTIVE
    instructions: str = ""
    total_marks: int = 0


class SubmitAnswerRequest(BaseModel):
    session_token: str
    question_id: str
    response: str
    time_taken_sec: float | None = None


class SubmitAnswerResponse(BaseModel):
    is_correct: bool | None
    marks_awarded: float
    next_question: QuestionStudentView | None
    attempt_status: AttemptStatus
    code_result: CodeRunSummary | None = None
    answered_question_ids: list[str] = Field(default_factory=list)


class FinishAttemptRequest(BaseModel):
    session_token: str


class FinishAttemptResponse(BaseModel):
    attempt_id: str
    status: AttemptStatus
    questions_answered: int
    total_marks: float
    max_possible_marks: int
    submitted_at: datetime | None


class RunCodeRequest(BaseModel):
    session_token: str
    question_id: str
    code: str


class RunCodeResponse(BaseModel):
    code_result: CodeRunSummary


class ViolationReportRequest(BaseModel):
    session_token: str
    type: str
    metadata: dict = Field(default_factory=dict)


class ViolationReportResponse(BaseModel):
    violation_count: int
    max_violations: int
    attempt_status: AttemptStatus
    auto_submitted: bool


class AttemptAnswerDetail(BaseModel):
    question_id: str
    type: QuestionType | None = None
    text: str
    response: str
    is_correct: bool | None
    marks_awarded: float
    max_marks: int
    code_result: CodeRunSummary | None = None
    # Revealed only after the attempt has been submitted.
    correct_answer: str | None = None
    explanation: str | None = None
    section: str | None = None
    # Manual grading (descriptive answers). ``graded_at`` is None while the
    # answer is still awaiting review.
    graded_at: datetime | None = None
    feedback: str | None = None


class AttemptResultResponse(BaseModel):
    attempt_id: str
    status: AttemptStatus
    total_marks: float
    max_possible_marks: int
    questions_answered: int
    started_at: datetime
    submitted_at: datetime | None
    answers: list[AttemptAnswerDetail] = Field(default_factory=list)


class AttemptQuestionsResponse(BaseModel):
    attempt_id: str
    format: AssessmentFormat
    total_questions: int
    questions: list[QuestionStudentView] = Field(default_factory=list)
    answered_question_ids: list[str] = Field(default_factory=list)
    instructions: str = ""


# ---------------------------------------------------------------------------
# Manual review of descriptive answers (TPO/admin)
# ---------------------------------------------------------------------------
class PendingReviewItem(BaseModel):
    attempt_id: str
    assessment_id: str
    assessment_title: str
    assessment_type: AssessmentType
    drive_id: str | None = None
    student_id: str
    student_name: str | None = None
    submitted_at: datetime | None = None
    pending_count: int
    total_answers: int


class AttemptReviewAnswer(BaseModel):
    question_id: str
    question_text: str
    response: str
    max_marks: int
    marks_awarded: float
    is_correct: bool | None
    graded_at: datetime | None = None
    feedback: str | None = None
    skill_tags: list[str] = Field(default_factory=list)


class AttemptReviewResponse(BaseModel):
    attempt_id: str
    assessment_id: str
    assessment_title: str
    assessment_type: AssessmentType
    drive_id: str | None = None
    student_id: str
    student_name: str | None = None
    status: AttemptStatus
    submitted_at: datetime | None = None
    pending_count: int
    total_marks: float
    max_possible_marks: int
    answers: list[AttemptReviewAnswer] = Field(default_factory=list)


class ManualGradeRequest(BaseModel):
    question_id: str
    marks_awarded: float = Field(ge=0)
    feedback: str | None = None


class ManualGradeResponse(BaseModel):
    attempt_id: str
    question_id: str
    marks_awarded: float
    is_correct: bool
    pending_count: int
    total_marks: float
    max_possible_marks: int


class KnowledgeStateResponse(BaseModel):
    skill_tag: str
    mastery_pct: float
    confidence: float
    attempts_count: int


# ---------------------------------------------------------------------------
# Question-bank management / import / export schemas
# ---------------------------------------------------------------------------
class QuestionStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    by_category: dict[str, int]
    by_difficulty: dict[str, int]
    by_type: dict[str, int]


class ImportRowError(BaseModel):
    row: int  # 1-based spreadsheet row number (header is row 1)
    field: str
    message: str


class ImportPreviewRow(BaseModel):
    row: int
    question: QuestionCreateRequest | None = None
    raw_text: str | None = None  # retained for invalid-row error reports
    errors: list[ImportRowError] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    filename: str
    detected_columns: dict[str, str]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    rows: list[ImportPreviewRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Reusable assessment templates
# ---------------------------------------------------------------------------
class TemplateStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class SectionConfig(BaseModel):
    name: str
    questions: int = Field(default=0, ge=0, le=100)
    category_ids: list[str] = Field(default_factory=list)
    difficulty: DifficultyLevel | None = None


class AssessmentTemplateInDB(MongoBaseModel):
    name: str
    description: str = ""
    category_ids: list[str] = Field(default_factory=list)
    sections: list[SectionConfig] = Field(default_factory=list)
    difficulty_distribution: dict[str, int] = Field(default_factory=dict)
    question_types: list[QuestionType] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    total_questions: int = 0
    total_marks: int = 0
    time_limit_sec: int = 1800
    passing_marks: int = 0
    negative_marks: float = 0.0
    instructions: str = ""
    randomize_options: bool = True
    allow_retake: bool = False
    status: TemplateStatus = TemplateStatus.ACTIVE
    format: AssessmentFormat = AssessmentFormat.ADAPTIVE
    preset_key: str | None = None
    created_by: PyObjectId
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None


class AssessmentTemplateUpsertRequest(BaseModel):
    name: str
    description: str = ""
    category_ids: list[str] = Field(default_factory=list)
    sections: list[SectionConfig] = Field(default_factory=list)
    difficulty_distribution: dict[str, int] = Field(default_factory=dict)
    question_types: list[QuestionType] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    total_questions: int = Field(default=0, ge=0, le=200)
    total_marks: int = Field(default=0, ge=0, le=2000)
    time_limit_sec: int = Field(default=1800, ge=60)
    passing_marks: int = Field(default=0, ge=0, le=2000)
    negative_marks: float = Field(default=0.0, ge=0.0, le=100.0)
    instructions: str = ""
    randomize_options: bool = True
    allow_retake: bool = False
    status: TemplateStatus = TemplateStatus.ACTIVE
    format: AssessmentFormat = AssessmentFormat.ADAPTIVE
    preset_key: str | None = None


class AssessmentTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    category_ids: list[str]
    sections: list[SectionConfig]
    difficulty_distribution: dict[str, int]
    question_types: list[QuestionType]
    topics: list[str]
    skills: list[str]
    total_questions: int
    total_marks: int
    time_limit_sec: int
    passing_marks: int
    negative_marks: float
    instructions: str
    randomize_options: bool
    allow_retake: bool
    status: TemplateStatus
    format: AssessmentFormat
    preset_key: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class TemplatePresetResponse(BaseModel):
    key: str
    name: str
    description: str
    config: AssessmentTemplateUpsertRequest


# ---------------------------------------------------------------------------
# Standardized placement-drive assessment generation
# ---------------------------------------------------------------------------
class PlacementSectionRequest(BaseModel):
    name: str
    category_ids: list[str] = Field(default_factory=list)
    skill_tags: list[str] = Field(default_factory=list)


class PlacementGenerationRequest(BaseModel):
    drive_id: str
    title: str | None = None
    time_limit_minutes: int = Field(default=30, ge=1, le=300)
    passing_marks: int = Field(default=0, ge=0, le=2000)
    negative_marks: float = Field(default=0.0, ge=0.0, le=100.0)
    instructions: str = ""
    allow_retake: bool = False
    sections: list[PlacementSectionRequest] = Field(default_factory=list)
    template_id: str | None = None
    publish: bool = False


class PlacementQuestionView(BaseModel):
    id: str
    text: str
    section: str
    difficulty: DifficultyLevel
    type: QuestionType
    topic: str | None = None
    skill: str | None = None
    marks: int


class PlacementGenerationResponse(BaseModel):
    assessment_id: str
    title: str
    drive_id: str
    format: AssessmentFormat
    status: AssessmentPublishStatus
    total_questions: int
    total_marks: int
    time_limit_sec: int
    sections: list[dict]
    questions: list[PlacementQuestionView]
    template_id: str | None = None
    deficit: list[str] = Field(default_factory=list)


class PlacementEligibilityResponse(BaseModel):
    can_generate: bool
    sections: list[dict]
    deficits: list[str] = Field(default_factory=list)


class PlacementParticipationResponse(BaseModel):
    drive_id: str
    assessment_id: str
    eligible_students: int
    attempts_started: int
    submitted: int
    in_progress: int
    students: list[dict] = Field(default_factory=list)


class PlacementRevisionRequest(BaseModel):
    confirm_republish: bool = False
    reason: str = ""
    time_limit_minutes: int | None = Field(default=None, ge=1, le=300)
    publish: bool = True
