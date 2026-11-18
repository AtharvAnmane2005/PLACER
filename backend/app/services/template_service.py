"""Reusable assessment templates — DB-backed configuration, never questions."""
from __future__ import annotations

from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.assessment import (
    PLACEMENT_DIFFICULTY_QUOTA,
    PLACEMENT_SECTIONS,
    AssessmentFormat,
    AssessmentTemplateInDB,
    AssessmentTemplateResponse,
    AssessmentTemplateUpsertRequest,
    DifficultyLevel,
    QuestionType,
    SectionConfig,
    TemplatePresetResponse,
    TemplateStatus,
)
from app.repositories.template_repository import AssessmentTemplateRepository


class TemplateError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _preset(
    key: str,
    name: str,
    description: str,
    *,
    sections: list[SectionConfig],
    distribution: dict[str, int],
    total_questions: int,
    total_marks: int,
    question_types: list[QuestionType],
    format: AssessmentFormat = AssessmentFormat.ADAPTIVE,
    passing_marks: int = 0,
    instructions: str = "",
) -> TemplatePresetResponse:
    return TemplatePresetResponse(
        key=key,
        name=name,
        description=description,
        config=AssessmentTemplateUpsertRequest(
            name=name,
            description=description,
            sections=sections,
            difficulty_distribution=distribution,
            total_questions=total_questions,
            total_marks=total_marks,
            question_types=question_types,
            time_limit_sec=1800,
            passing_marks=passing_marks,
            instructions=instructions,
            format=format,
            preset_key=key,
        ),
    )


# Predefined *configurations*. Administrators edit and save them as real
# template documents; none of these contain question content or answers.
TEMPLATE_PRESETS: list[TemplatePresetResponse] = [
    _preset(
        "technical",
        "Technical Assessment",
        "Mixed technical screen across core engineering topics.",
        sections=[SectionConfig(name="Technical Knowledge", questions=10)],
        distribution={"easy": 3, "medium": 5, "hard": 2},
        total_questions=10,
        total_marks=30,
        question_types=[QuestionType.MCQ, QuestionType.TRUE_FALSE],
        passing_marks=12,
    ),
    _preset(
        "aptitude",
        "Aptitude Assessment",
        "Numerical ability and quantitative reasoning practice.",
        sections=[SectionConfig(name="Quantitative Aptitude", questions=10)],
        distribution={"easy": 4, "medium": 4, "hard": 2},
        total_questions=10,
        total_marks=30,
        question_types=[QuestionType.MCQ],
        passing_marks=12,
    ),
    _preset(
        "logical_reasoning",
        "Logical Reasoning Assessment",
        "Deduction, patterns and analytical reasoning.",
        sections=[SectionConfig(name="Logical Reasoning", questions=10)],
        distribution={"easy": 3, "medium": 5, "hard": 2},
        total_questions=10,
        total_marks=30,
        question_types=[QuestionType.MCQ],
        passing_marks=12,
    ),
    _preset(
        "verbal_ability",
        "Verbal Ability Assessment",
        "Reading comprehension, grammar and vocabulary.",
        sections=[SectionConfig(name="Verbal Ability", questions=10)],
        distribution={"easy": 4, "medium": 4, "hard": 2},
        total_questions=10,
        total_marks=30,
        question_types=[QuestionType.MCQ, QuestionType.TRUE_FALSE],
        passing_marks=12,
    ),
    _preset(
        "programming",
        "Programming Assessment",
        "Data structures, algorithms and problem solving.",
        sections=[SectionConfig(name="Programming / Problem Solving", questions=10)],
        distribution={"easy": 3, "medium": 5, "hard": 2},
        total_questions=10,
        total_marks=30,
        question_types=[QuestionType.MCQ, QuestionType.MULTIPLE_SELECT, QuestionType.CODING],
        passing_marks=12,
    ),
    _preset(
        "placement_drive_mock",
        "Placement Drive Mock Assessment",
        "Standardized 20-question, five-section placement drive test.",
        sections=[SectionConfig(name=name, questions=4) for name in PLACEMENT_SECTIONS],
        distribution={d.value: n for d, n in PLACEMENT_DIFFICULTY_QUOTA.items()},
        total_questions=20,
        total_marks=60,
        question_types=[QuestionType.MCQ, QuestionType.MULTIPLE_SELECT, QuestionType.TRUE_FALSE],
        format=AssessmentFormat.STANDARDIZED,
        passing_marks=30,
        instructions="20 questions. 4 from each section. 30 minutes. Answer all questions.",
    ),
    _preset(
        "custom",
        "Custom Assessment",
        "Start from an empty configuration.",
        sections=[],
        distribution={"easy": 0, "medium": 0, "hard": 0},
        total_questions=0,
        total_marks=0,
        question_types=[],
    ),
]


class TemplateService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.templates = AssessmentTemplateRepository(db)
        self.db = db

    @staticmethod
    def presets() -> list[TemplatePresetResponse]:
        return TEMPLATE_PRESETS

    @staticmethod
    def to_response(template: AssessmentTemplateInDB) -> AssessmentTemplateResponse:
        return AssessmentTemplateResponse(
            id=template.id,
            name=template.name,
            description=template.description,
            category_ids=template.category_ids,
            sections=template.sections,
            difficulty_distribution=template.difficulty_distribution,
            question_types=template.question_types,
            topics=template.topics,
            skills=template.skills,
            total_questions=template.total_questions,
            total_marks=template.total_marks,
            time_limit_sec=template.time_limit_sec,
            passing_marks=template.passing_marks,
            negative_marks=template.negative_marks,
            instructions=template.instructions,
            randomize_options=template.randomize_options,
            allow_retake=template.allow_retake,
            status=template.status,
            format=template.format,
            preset_key=template.preset_key,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

    async def _resolve_categories(self, payload: AssessmentTemplateUpsertRequest) -> None:
        """Presets use category names so they stay portable across databases."""
        from bson import ObjectId

        from app.repositories.question_repository import QuestionCategoryRepository

        repository = QuestionCategoryRepository(self.db)
        all_categories = await repository.find_many({}, limit=500)
        by_name = {c.name.lower(): c.id for c in all_categories}
        by_id = {c.id for c in all_categories}

        def resolve(value: str) -> str:
            if value in by_id:
                return value
            if ObjectId.is_valid(value) and value in by_id:
                return value
            if value.lower() in by_name:
                return by_name[value.lower()]
            return value  # leave unknown values to fail validation during generation

        payload.category_ids = [resolve(c) for c in payload.category_ids]
        for section in payload.sections:
            section.category_ids = [resolve(c) for c in section.category_ids]

    def _validate(self, payload: AssessmentTemplateUpsertRequest) -> None:
        if not payload.name.strip():
            raise TemplateError("Template name is required.")
        if not payload.sections:
            raise TemplateError("At least one section is required.")
        configured = sum(section.questions for section in payload.sections)
        if payload.total_questions and configured != payload.total_questions:
            raise TemplateError(
                f"Section question counts ({configured}) must add up to total_questions "
                f"({payload.total_questions})."
            )
        if payload.format == AssessmentFormat.STANDARDIZED:
            if payload.total_questions != 20 or configured != 20:
                raise TemplateError("A standardized assessment template must configure exactly 20 questions.")
            if len(payload.sections) != 5 or any(section.questions != 4 for section in payload.sections):
                raise TemplateError("A standardized template must have five sections of four questions each.")
            expected = {d.value: n for d, n in PLACEMENT_DIFFICULTY_QUOTA.items()}
            if dict(payload.difficulty_distribution) != expected:
                raise TemplateError("A standardized template must use the 6 easy / 10 medium / 4 hard distribution.")

    async def create(self, payload: AssessmentTemplateUpsertRequest, admin_user_id: str) -> AssessmentTemplateInDB:
        self._validate(payload)
        await self._resolve_categories(payload)
        return await self.templates.create(
            {
                **payload.model_dump(mode="json"),
                "created_by": admin_user_id,
                "created_at": datetime.utcnow(),
                "updated_at": None,
            }
        )

    async def update(self, template_id: str, payload: AssessmentTemplateUpsertRequest) -> AssessmentTemplateInDB:
        existing = await self.templates.get_by_id(template_id)
        if not existing:
            raise TemplateError("Template not found.", 404)
        self._validate(payload)
        await self._resolve_categories(payload)
        updated = await self.templates.update_by_id(
            template_id, {**payload.model_dump(mode="json"), "updated_at": datetime.utcnow()}
        )
        return updated

    async def duplicate(self, template_id: str, admin_user_id: str) -> AssessmentTemplateInDB:
        original = await self.templates.get_by_id(template_id)
        if not original:
            raise TemplateError("Template not found.", 404)
        data = original.model_dump(mode="json")
        data.pop("id", None)
        data.pop("preset_key", None)
        data["name"] = f"{original.name} (copy)"
        data["created_by"] = admin_user_id
        data["created_at"] = datetime.utcnow()
        data["updated_at"] = None
        return await self.templates.create(data)

    async def set_status(self, template_id: str, status: TemplateStatus) -> AssessmentTemplateInDB:
        updated = await self.templates.update_by_id(
            template_id, {"status": status.value, "updated_at": datetime.utcnow()}
        )
        if not updated:
            raise TemplateError("Template not found.", 404)
        return updated

    async def delete(self, template_id: str) -> None:
        if not await self.templates.delete_by_id(template_id):
            raise TemplateError("Template not found.", 404)

    async def get(self, template_id: str) -> AssessmentTemplateInDB:
        template = await self.templates.get_by_id(template_id)
        if not template:
            raise TemplateError("Template not found.", 404)
        return template

    async def list(self, status: str | None = None) -> list[AssessmentTemplateInDB]:
        query = {"status": status} if status in {"active", "inactive"} else {}
        return await self.templates.find_many(query, limit=200)
