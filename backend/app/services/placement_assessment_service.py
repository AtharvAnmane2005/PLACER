"""Standardized placement-drive assessment generation.

Every generated assessment contains exactly 20 questions: four from each of
five sections and a 6/10/4 easy/medium/hard mix. The question set, its order,
marks and duration are stored once on the assessment and reused by every
student in the drive. No questions are invented here — an insufficient bank
produces an explicit, actionable deficit error.
"""
from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.assessment import (
    PLACEMENT_DIFFICULTY_QUOTA,
    PLACEMENT_SECTION_SIZE,
    PLACEMENT_SECTIONS,
    PLACEMENT_TOTAL_QUESTIONS,
    OBJECTIVE_QUESTION_TYPES,
    AssessmentFormat,
    AssessmentInDB,
    AttemptStatus,
    AssessmentPublishStatus,
    AssessmentType,
    PlacementEligibilityResponse,
    PlacementGenerationRequest,
    PlacementGenerationResponse,
    PlacementParticipationResponse,
    PlacementQuestionView,
    PlacementRevisionRequest,
    PlacementSectionRequest,
)
from app.models.drive import AssessmentStatus
from app.repositories.activity_log_repository import log_activity
from app.repositories.application_repository import ApplicationRepository
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.attempt_repository import AttemptRepository
from app.repositories.drive_repository import PlacementDriveRepository
from app.repositories.question_repository import QuestionCategoryRepository
from app.services.assessment_selection_service import QuestionSelector
from app.services.template_service import TemplateError, TemplateService

# Default section -> existing category names. Administrators can override
# per generation; admins must add a real "Verbal Ability" category + questions
# before a fully balanced assessment can be generated.
DEFAULT_SECTION_CATEGORY_NAMES: dict[str, tuple[str, ...]] = {
    "Quantitative Aptitude": ("Aptitude & Logical Reasoning",),
    "Logical Reasoning": ("Aptitude & Logical Reasoning",),
    "Verbal Ability": ("Verbal Ability",),
    "Technical Knowledge": (
        "DBMS & SQL",
        "Operating Systems",
        "Computer Networks",
        "Object-Oriented Programming",
        "Machine Learning & AI",
        "Cybersecurity",
        "Cloud & DevOps",
        "Software Engineering",
    ),
    "Programming / Problem Solving": (
        "Data Structures & Algorithms",
        "Python Programming",
        "JavaScript & Web Development",
    ),
}


class PlacementGenerationError(Exception):
    def __init__(self, message: str, status_code: int = 422, deficits: list[str] | None = None):
        self.message = message
        self.status_code = status_code
        self.deficits = deficits or []
        super().__init__(message)


class PlacementAssessmentService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.drives = PlacementDriveRepository(db)
        self.assessments = AssessmentRepository(db)
        self.categories = QuestionCategoryRepository(db)
        self.selector = QuestionSelector(db)

    async def _category_id_map(self) -> dict[str, str]:
        categories = await self.categories.find_many({}, limit=500)
        return {c.name.lower(): c.id for c in categories}

    async def _resolve_request(
        self, request: PlacementGenerationRequest
    ) -> tuple[PlacementGenerationRequest, object | None]:
        """Apply a saved template's configuration to an explicit request.

        Values explicitly supplied in the API payload always win; the template
        fills only the fields the administrator left out.
        """
        if not request.template_id:
            return request, None
        try:
            template = await TemplateService(self.db).get(request.template_id)
        except TemplateError as exc:
            raise PlacementGenerationError(exc.message, exc.status_code) from exc
        if template.format != AssessmentFormat.STANDARDIZED:
            raise PlacementGenerationError("The selected template is not a standardized assessment template.", 400)
        if template.status.value != "active":
            raise PlacementGenerationError("Inactive templates cannot be used to generate assessments.", 400)

        updates: dict = {}
        if not request.sections:
            updates["sections"] = [
                PlacementSectionRequest(
                    name=section.name,
                    category_ids=list(section.category_ids),
                    skill_tags=[],
                )
                for section in template.sections
            ]
        explicit = request.model_fields_set
        if "title" not in explicit and not request.title:
            updates["title"] = template.name
        if "time_limit_minutes" not in explicit:
            updates["time_limit_minutes"] = max(1, round(template.time_limit_sec / 60))
        if "passing_marks" not in explicit:
            updates["passing_marks"] = template.passing_marks
        if "negative_marks" not in explicit:
            updates["negative_marks"] = template.negative_marks
        if "instructions" not in explicit and not request.instructions:
            updates["instructions"] = template.instructions
        if "allow_retake" not in explicit:
            updates["allow_retake"] = template.allow_retake
        return request.model_copy(update=updates), template

    async def _resolve_sections(self, request: PlacementGenerationRequest) -> list[dict]:
        category_map = await self._category_id_map()
        if request.sections:
            sections = []
            for section in request.sections:
                resolved = []
                for value in section.category_ids:
                    if ObjectId.is_valid(value) and value in category_map.values():
                        resolved.append(value)
                    elif value.lower() in category_map:
                        resolved.append(category_map[value.lower()])
                if not resolved:
                    # A saved template may name a standard section without
                    # pinning category IDs; use the configured defaults.
                    resolved = [
                        category_map[category_name.lower()]
                        for category_name in DEFAULT_SECTION_CATEGORY_NAMES.get(section.name, ())
                        if category_name.lower() in category_map
                    ]
                sections.append(
                    {
                        "name": section.name,
                        "questions": PLACEMENT_SECTION_SIZE,
                        "category_ids": resolved,
                        "skill_tags": section.skill_tags,
                    }
                )
            return sections

        sections = []
        for name in PLACEMENT_SECTIONS:
            resolved = [
                category_map[category_name.lower()]
                for category_name in DEFAULT_SECTION_CATEGORY_NAMES.get(name, ())
                if category_name.lower() in category_map
            ]
            sections.append(
                {
                    "name": name,
                    "questions": PLACEMENT_SECTION_SIZE,
                    "category_ids": resolved,
                    "skill_tags": [],
                }
            )
        return sections

    async def _select(self, request: PlacementGenerationRequest, template: object | None = None):
        sections = await self._resolve_sections(request)
        structural_deficits = []
        for section in sections:
            if section["category_ids"]:
                continue
            expected = DEFAULT_SECTION_CATEGORY_NAMES.get(section["name"], ())
            expected_text = ", ".join(expected) if expected else "an explicit section category"
            structural_deficits.append(
                f"{section['name']}: no category is configured for this section "
                f"(expected {expected_text}); the 20-question bank requires "
                f"6 Easy, 10 Medium and 4 Hard questions."
            )
        if structural_deficits:
            return sections, [], structural_deficits
        if len(sections) != 5 or any(section["questions"] != PLACEMENT_SECTION_SIZE for section in sections):
            return sections, [], ["Standardized assessments require five sections of exactly 4 questions."]

        result = await self.selector.select(
            sections=sections,
            distribution={d.value: n for d, n in PLACEMENT_DIFFICULTY_QUOTA.items()},
            question_types=list(template.question_types) if template else list(OBJECTIVE_QUESTION_TYPES),
            topics=list(template.topics) if template else [],
            skills=list(template.skills) if template else [],
        )
        return sections, result, result.deficits

    async def eligibility(self, drive_id: str, request: PlacementGenerationRequest | None = None) -> PlacementEligibilityResponse:
        drive = await self.drives.get_by_id(drive_id)
        if not drive:
            raise PlacementGenerationError("Placement drive not found.", 404)
        request = request or PlacementGenerationRequest(drive_id=drive_id)
        request, template = await self._resolve_request(request)
        sections, result, deficits = await self._select(request, template)
        return PlacementEligibilityResponse(
            can_generate=not deficits,
            sections=[
                {
                    "name": section["name"],
                    "questions": section["questions"],
                    "category_ids": section["category_ids"],
                    "selected": len(result.sections[index].question_ids) if result else 0,
                }
                for index, section in enumerate(sections)
            ],
            deficits=deficits,
        )

    async def generate(
        self, request: PlacementGenerationRequest, admin_user_id: str, ip_address: str | None = None
    ) -> PlacementGenerationResponse:
        drive = await self.drives.get_by_id(request.drive_id)
        if not drive:
            raise PlacementGenerationError("Placement drive not found.", 404)
        request, template = await self._resolve_request(request)
        sections, result, deficits = await self._select(request, template)
        if deficits or result is None:
            raise PlacementGenerationError(
                "Cannot generate a standardized assessment: " + " ".join(deficits),
                422,
                deficits,
            )
        if len(result.questions) != PLACEMENT_TOTAL_QUESTIONS:
            raise PlacementGenerationError(
                f"Expected exactly {PLACEMENT_TOTAL_QUESTIONS} questions, got {len(result.questions)}.",
                422,
            )

        now = datetime.utcnow()
        question_ids = [q.id for q in result.questions]
        total_marks = sum(q.marks for q in result.questions)
        section_metadata = [
            {
                "name": item.name,
                "question_ids": item.question_ids,
                "difficulties": item.difficulties,
                "count": len(item.question_ids),
            }
            for item in result.sections
        ]
        title = (request.title or f"{drive.job_title} - Standardized Placement Assessment").strip()
        status = AssessmentPublishStatus.PUBLISHED if request.publish else AssessmentPublishStatus.DRAFT

        assessment = await self.assessments.create(
            {
                "title": title,
                "category_ids": sorted({c for section in sections for c in section["category_ids"]}),
                "question_pool_size": PLACEMENT_TOTAL_QUESTIONS,
                "time_limit_sec": request.time_limit_minutes * 60,
                "anti_cheat_config": {"max_violations": 3, "require_fullscreen": True},
                "type": AssessmentType.DRIVE.value,
                "drive_id": drive.id,
                "created_by": admin_user_id,
                "created_at": now,
                "format": AssessmentFormat.STANDARDIZED.value,
                "status": status.value,
                "question_ids": question_ids,
                "sections": section_metadata,
                "total_marks": total_marks,
                "passing_marks": request.passing_marks,
                "negative_marks": request.negative_marks,
                "instructions": request.instructions or "Answer all 20 questions. Same questions for every student.",
                "allow_retake": request.allow_retake,
                "randomize_options": True,
                "template_id": request.template_id,
                "generated_at": now,
                "published_at": now if request.publish else None,
            }
        )

        # Make this the drive's required assessment so all applications share it.
        await self.drives.update_by_id(drive.id, {"required_assessment_id": assessment.id})
        await log_activity(
            self.db,
            admin_user_id,
            action="placement_assessment_generated",
            entity="assessment",
            entity_id=assessment.id,
            metadata={
                "drive_id": drive.id,
                "question_count": len(question_ids),
                "status": status.value,
                "sections": [item["name"] for item in section_metadata],
            },
            ip_address=ip_address,
        )

        question_by_id = {q.id: q for q in result.questions}
        section_by_question: dict[str, str] = {}
        for item in result.sections:
            for question_id, difficulty in zip(item.question_ids, item.difficulties):
                question = question_by_id[question_id]
                section_by_question[question_id] = item.name
        return PlacementGenerationResponse(
            assessment_id=assessment.id,
            title=assessment.title,
            drive_id=drive.id,
            format=AssessmentFormat.STANDARDIZED,
            status=status,
            total_questions=len(question_ids),
            total_marks=total_marks,
            time_limit_sec=assessment.time_limit_sec,
            sections=section_metadata,
            template_id=request.template_id,
            questions=[
                PlacementQuestionView(
                    id=q.id,
                    text=q.text,
                    section=section_by_question[q.id],
                    difficulty=q.difficulty,
                    type=q.type,
                    topic=q.topic,
                    skill=q.skill or (q.skill_tags[0] if q.skill_tags else None),
                    marks=q.marks,
                )
                for q in result.questions
            ],
        )

    async def revise(
        self,
        assessment_id: str,
        request: PlacementRevisionRequest,
        admin_user_id: str,
        ip_address: str | None = None,
    ) -> PlacementGenerationResponse:
        assessment = await self.assessments.get_by_id(assessment_id)
        if not assessment:
            raise PlacementGenerationError("Assessment not found.", 404)
        if assessment.format != AssessmentFormat.STANDARDIZED:
            raise PlacementGenerationError("Only standardized assessments can be revised.", 400)
        if assessment.status == AssessmentPublishStatus.PUBLISHED and not request.confirm_republish:
            raise PlacementGenerationError(
                "This assessment is published. Set confirm_republish=true to authorize a new question set.",
                409,
            )
        if not assessment.drive_id:
            raise PlacementGenerationError("This assessment is not linked to a drive.", 400)

        generation_request = PlacementGenerationRequest(
            drive_id=assessment.drive_id,
            title=assessment.title,
            time_limit_minutes=(
                request.time_limit_minutes if request.time_limit_minutes else assessment.time_limit_sec // 60
            ),
            passing_marks=assessment.passing_marks,
            negative_marks=assessment.negative_marks,
            instructions=assessment.instructions,
            allow_retake=assessment.allow_retake,
            publish=request.publish,
        )
        result = await self.generate(generation_request, admin_user_id, ip_address)
        await log_activity(
            self.db,
            admin_user_id,
            action="placement_assessment_revised",
            entity="assessment",
            entity_id=assessment_id,
            metadata={"reason": request.reason, "new_assessment_id": result.assessment_id},
            ip_address=ip_address,
        )
        return result

    async def participation(self, drive_id: str, assessment_id: str) -> PlacementParticipationResponse:
        drive = await self.drives.get_by_id(drive_id)
        if not drive:
            raise PlacementGenerationError("Placement drive not found.", 404)
        applications = await ApplicationRepository(self.db).find_many({"drive_id": drive_id}, limit=1000)
        attempts = await AttemptRepository(self.db).find_many({"assessment_id": assessment_id}, limit=1000)
        attempts_by_student: dict[str, list] = {}
        for attempt in attempts:
            attempts_by_student.setdefault(attempt.student_id, []).append(attempt)
        students = []
        # These are attempt-level counts, not per-student classifications: an
        # allowed retake can leave one submitted and one in-progress attempt
        # for the same application, and both are real participation records.
        submitted = sum(1 for attempt in attempts if attempt.status == AttemptStatus.SUBMITTED)
        in_progress = sum(1 for attempt in attempts if attempt.status == AttemptStatus.IN_PROGRESS)
        for application in applications:
            student_attempts = attempts_by_student.get(application.student_id, [])
            statuses = [attempt.status.value for attempt in student_attempts]
            students.append(
                {
                    "student_id": application.student_id,
                    "application_id": application.id,
                    "application_status": application.status,
                    "assessment_status": application.assessment_status,
                    "attempt_count": len(student_attempts),
                    "attempt_statuses": statuses,
                }
            )
        return PlacementParticipationResponse(
            drive_id=drive_id,
            assessment_id=assessment_id,
            eligible_students=len(applications),
            attempts_started=len(attempts),
            submitted=submitted,
            in_progress=in_progress,
            students=students,
        )
