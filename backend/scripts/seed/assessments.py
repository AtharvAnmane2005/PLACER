"""Seed assessment templates, practice assessments and drive assessments.

Three layers, all reusing the application's own selection and generation
services (no questions are invented here):

* **Templates** — the reusable configurations exposed by ``TemplateService``.
  ``custom`` is deliberately skipped: it is a UI starting point with zero
  sections, and ``TemplateService`` correctly refuses to persist an empty
  template.
* **Practice** — five adaptive practice papers (created exactly like the admin
  ``POST /assessments`` route) plus two fixed-set standardized practice
  papers. One of the fixed papers is a 20-question placement mock and the
  other is a coding-only paper, so coding questions are demonstrably
  selectable in practice and graded by the same backend runner.
* **Drive** — one standardized 20-question paper per seeded drive, generated
  through ``PlacementAssessmentService``. Each drive gets a different,
  reproducible question set via the selector's optional ``seed`` argument,
  and the drive is updated with its minimum score and assessment deadline.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.assessment import (
    PLACEMENT_DIFFICULTY_QUOTA,
    AssessmentFormat,
    AssessmentPublishStatus,
    AssessmentType,
    PlacementGenerationRequest,
    QuestionType,
)
from app.models.drive import DriveUpdateRequest
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.drive_repository import PlacementDriveRepository
from app.repositories.template_repository import AssessmentTemplateRepository
from app.services.assessment_selection_service import QuestionSelector
from app.services.assessment_service import AssessmentService
from app.services.drive_service import DriveError, DriveService
from app.services.placement_assessment_service import (
    PlacementAssessmentService,
    PlacementGenerationError,
)
from app.services.template_service import TEMPLATE_PRESETS, TemplateService

from scripts.seed.context import SYNTHETIC, category_id, now, stable_oid

# ---------------------------------------------------------------------------
# Practice papers
# ---------------------------------------------------------------------------
ADAPTIVE_PRACTICE: list[dict] = [
    {
        "title": "Full-Stack Placement Readiness - Practice",
        "categories": [
            "Data Structures & Algorithms",
            "DBMS & SQL",
            "Operating Systems",
            "Computer Networks",
            "Object-Oriented Programming",
            "Python Programming",
            "JavaScript & Web Development",
            "Aptitude & Logical Reasoning",
            "Machine Learning & AI",
            "Cybersecurity",
            "Cloud & DevOps",
            "Software Engineering",
            "Verbal Ability",
        ],
        "question_pool_size": 10,
        "time_limit_sec": 1800,
    },
    {
        "title": "Data Structures & Algorithms Sprint - Practice",
        "categories": [
            "Data Structures & Algorithms",
            "Python Programming",
            "Object-Oriented Programming",
        ],
        "question_pool_size": 8,
        "time_limit_sec": 1200,
    },
    {
        "title": "SQL & Data Analysis Drill - Practice",
        "categories": [
            "DBMS & SQL",
            "Aptitude & Logical Reasoning",
            "Machine Learning & AI",
        ],
        "question_pool_size": 8,
        "time_limit_sec": 1200,
    },
    {
        "title": "Cybersecurity & Networks Drill - Practice",
        "categories": [
            "Cybersecurity",
            "Computer Networks",
            "Operating Systems",
        ],
        "question_pool_size": 8,
        "time_limit_sec": 1200,
    },
    {
        "title": "Software Engineering & OOP Drill - Practice",
        "categories": [
            "Software Engineering",
            "Object-Oriented Programming",
            "JavaScript & Web Development",
        ],
        "question_pool_size": 8,
        "time_limit_sec": 1200,
    },
]

# Fixed-set practice papers are created with the same selector used by drive
# generation. The standardized format is intentionally not exposed through
# the simple admin create route (that route requires the placement generation
# endpoint), but a seeded practice paper is a normal standardized assessment
# document and uses the identical attempt/grading path.
STANDARDIZED_PRACTICE: list[dict] = [
    {
        "title": "Placement Drive Mock - Practice",
        "seed": 9001,
        "time_limit_sec": 1800,
        "passing_marks": 28,
        "instructions": (
            "20 questions across five sections, 30 minutes. "
            "Includes one coding question graded against hidden tests."
        ),
        "sections": [
            {
                "name": name,
                "questions": 4,
                "category_ids": [category_id(name) for name in _categories],
                "coding_questions": 1 if name == "Programming / Problem Solving" else 0,
            }
            for name, _categories in (
                ("Quantitative Aptitude", ("Aptitude & Logical Reasoning",)),
                ("Logical Reasoning", ("Aptitude & Logical Reasoning",)),
                ("Verbal Ability", ("Verbal Ability",)),
                (
                    "Technical Knowledge",
                    (
                        "DBMS & SQL",
                        "Operating Systems",
                        "Computer Networks",
                        "Object-Oriented Programming",
                        "Machine Learning & AI",
                        "Cybersecurity",
                        "Cloud & DevOps",
                        "Software Engineering",
                    ),
                ),
                (
                    "Programming / Problem Solving",
                    (
                        "Data Structures & Algorithms",
                        "Python Programming",
                        "JavaScript & Web Development",
                    ),
                ),
            )
        ],
        "distribution": {d.value: n for d, n in PLACEMENT_DIFFICULTY_QUOTA.items()},
    },
    {
        "title": "Coding Interview Practice - Python & JavaScript",
        "seed": 9002,
        "time_limit_sec": 3600,
        "passing_marks": 32,
        "instructions": (
            "20 coding questions, 60 minutes. Each answer is executed against "
            "the question's visible sample and hidden tests."
        ),
        "sections": [
            {
                "name": name,
                "questions": 4,
                "category_ids": [
                    category_id("Data Structures & Algorithms"),
                    category_id("Python Programming"),
                    category_id("JavaScript & Web Development"),
                ],
                "coding_questions": 4,
            }
            for name in (
                "Coding Fundamentals",
                "Data Structures",
                "Algorithms",
                "Problem Solving",
                "Optimisation",
            )
        ],
        # The coding bank has 12 easy, 26 medium and 22 hard questions. This
        # mix is deliberately coding-heavy but still uses all three levels.
        "distribution": {"easy": 4, "medium": 10, "hard": 6},
    },
]


async def _seed_templates(db: AsyncIOMotorDatabase, admin_user_id: str, log=print) -> int:
    repository = AssessmentTemplateRepository(db)
    service = TemplateService(db)
    created = 0
    for preset in TEMPLATE_PRESETS:
        if preset.key == "custom":
            log("  SKIP   Custom Assessment (UI-only empty starting point)")
            continue
        existing = await repository.find_one({"preset_key": preset.key})
        if existing:
            log(f"  REUSE  {preset.name}")
            continue
        template = await service.create(preset.config, admin_user_id)
        await db.assessment_templates.update_one(
            {"_id": ObjectId(template.id)}, {"$set": {**SYNTHETIC, "seed_note": "seed/assessments.py"}}
        )
        created += 1
        log(f"  CREATE {preset.name}")
    return created


async def _seed_adaptive_practice(
    db: AsyncIOMotorDatabase, admin_user_id: str, log=print
) -> list[str]:
    assessments = AssessmentRepository(db)
    service = AssessmentService(db)
    ids: list[str] = []
    for spec in ADAPTIVE_PRACTICE:
        category_ids = [str(category_id(name)) for name in spec["categories"]]
        total_marks = await service.compute_adaptive_total_marks(
            category_ids, spec["question_pool_size"]
        )
        existing = await assessments.find_one({"title": spec["title"]})
        if existing:
            if not existing.total_marks:
                await assessments.update_by_id(existing.id, {"total_marks": total_marks})
            ids.append(existing.id)
            log(f"  REUSE  {spec['title']} ({total_marks} marks)")
            continue
        assessment = await assessments.create(
            {
                "_id": stable_oid(f"assessment:practice:{spec['title']}"),
                "title": spec["title"],
                "category_ids": category_ids,
                "question_pool_size": spec["question_pool_size"],
                "time_limit_sec": spec["time_limit_sec"],
                "anti_cheat_config": {"max_violations": 3, "require_fullscreen": True},
                "type": AssessmentType.PRACTICE.value,
                "created_by": admin_user_id,
                "created_at": now(),
                "format": AssessmentFormat.ADAPTIVE.value,
                "status": AssessmentPublishStatus.PUBLISHED.value,
                "instructions": "Adaptive practice. Difficulty changes with your answers.",
                "allow_retake": True,
                "randomize_options": True,
                "total_marks": total_marks,
                "published_at": now(),
                **SYNTHETIC,
            }
        )
        ids.append(assessment.id)
        log(f"  CREATE {spec['title']} ({total_marks} marks)")
    return ids


async def _seed_standardized_practice(
    db: AsyncIOMotorDatabase, admin_user_id: str, log=print
) -> list[str]:
    assessments = AssessmentRepository(db)
    selector = QuestionSelector(db)
    ids: list[str] = []
    for spec in STANDARDIZED_PRACTICE:
        existing = await assessments.find_one({"title": spec["title"]})
        if existing:
            ids.append(existing.id)
            log(f"  REUSE  {spec['title']}")
            continue

        result = await selector.select(
            sections=spec["sections"],
            distribution=spec["distribution"],
            question_types=[QuestionType.CODING]
            if spec["title"].startswith("Coding Interview")
            else list(
                (
                    QuestionType.MCQ,
                    QuestionType.MULTIPLE_SELECT,
                    QuestionType.TRUE_FALSE,
                )
            ),
            seed=spec["seed"],
        )
        if result.deficits:
            raise RuntimeError(
                f"Cannot build practice assessment {spec['title']!r}: "
                + " ".join(result.deficits)
            )
        question_ids = [question.id for question in result.questions]
        if len(question_ids) != 20:
            raise RuntimeError(
                f"Practice assessment {spec['title']!r} selected "
                f"{len(question_ids)} questions, expected 20."
            )

        sections = [
            {
                "name": item.name,
                "question_ids": item.question_ids,
                "difficulties": item.difficulties,
                "count": len(item.question_ids),
            }
            for item in result.sections
        ]
        total_marks = sum(question.marks for question in result.questions)
        assessment = await assessments.create(
            {
                "_id": stable_oid(f"assessment:practice:{spec['title']}"),
                "title": spec["title"],
                "category_ids": sorted(
                    {str(c) for section in spec["sections"] for c in section["category_ids"]}
                ),
                "question_pool_size": 20,
                "time_limit_sec": spec["time_limit_sec"],
                "anti_cheat_config": {"max_violations": 3, "require_fullscreen": True},
                "type": AssessmentType.PRACTICE.value,
                "created_by": admin_user_id,
                "created_at": now(),
                "format": AssessmentFormat.STANDARDIZED.value,
                "status": AssessmentPublishStatus.PUBLISHED.value,
                "question_ids": question_ids,
                "sections": sections,
                "total_marks": total_marks,
                "passing_marks": spec["passing_marks"],
                "negative_marks": 0.0,
                "instructions": spec["instructions"],
                "allow_retake": True,
                "randomize_options": True,
                "template_id": None,
                "generated_at": now(),
                "published_at": now(),
                **SYNTHETIC,
            }
        )
        ids.append(assessment.id)
        coding_count = sum(
            1
            for question in result.questions
            if question.type == QuestionType.CODING
        )
        log(
            f"  CREATE {spec['title']} ({len(question_ids)} questions, "
            f"{coding_count} coding, {total_marks} marks)"
        )
    return ids


async def _seed_drive_assessments(
    db: AsyncIOMotorDatabase,
    admin_user_id: str,
    tpo_user_id: str,
    log=print,
) -> list[str]:
    drives = await PlacementDriveRepository(db).find_many({}, limit=500, sort=[("created_at", 1)])
    service = PlacementAssessmentService(db)
    drive_service = DriveService(db)
    ids: list[str] = []

    for index, drive in enumerate(drives):
        if drive.required_assessment_id:
            ids.append(str(drive.required_assessment_id))
            log(f"  REUSE  {drive.job_title} (already has an assessment)")
            continue

        request = PlacementGenerationRequest(
            drive_id=drive.id,
            title=f"{drive.job_title} - Standardized Placement Assessment",
            time_limit_minutes=30,
            passing_marks=28,
            negative_marks=0.0,
            instructions=(
                "20 questions across five sections, 30 minutes. "
                "Includes one coding question graded against hidden tests."
            ),
            allow_retake=False,
            publish=True,
        )
        try:
            result = await service.generate(
                request, admin_user_id, seed=1000 + index
            )
        except PlacementGenerationError as exc:
            raise RuntimeError(
                f"Cannot generate assessment for drive {drive.job_title!r}: "
                f"{exc.message} {' '.join(exc.deficits)}".strip()
            ) from exc

        deadline = drive.deadline - timedelta(days=2)
        if deadline <= datetime.utcnow():
            deadline = datetime.utcnow() + timedelta(days=7)
        try:
            await drive_service.update_drive(
                tpo_user_id,
                drive.id,
                DriveUpdateRequest(
                    assessment_min_score_pct=50.0,
                    assessment_deadline=deadline,
                ),
            )
        except DriveError as exc:
            raise RuntimeError(
                f"Cannot update assessment rules for drive {drive.job_title!r}: {exc.message}"
            ) from exc

        ids.append(result.assessment_id)
        log(
            f"  CREATE {drive.job_title:<34} "
            f"{result.total_questions} questions / {result.total_marks} marks "
            f"(min 50%, deadline {deadline:%Y-%m-%d})"
        )

    return ids


async def seed_assessments(
    db: AsyncIOMotorDatabase,
    admin_user_id: str,
    tpo_user_id: str,
    log=print,
) -> dict:
    log("Templates:")
    templates_created = await _seed_templates(db, admin_user_id, log=log)

    log("\nAdaptive practice assessments:")
    adaptive = await _seed_adaptive_practice(db, admin_user_id, log=log)

    log("\nStandardized practice assessments:")
    standardized = await _seed_standardized_practice(db, admin_user_id, log=log)

    log("\nDrive assessments:")
    drive_ids = await _seed_drive_assessments(db, admin_user_id, tpo_user_id, log=log)

    total = await db.assessments.count_documents({})
    practice = await db.assessments.count_documents({"type": "practice"})
    drive = await db.assessments.count_documents({"type": "drive"})
    templates = await db.assessment_templates.count_documents({})
    linked = await db.placement_drives.count_documents(
        {"required_assessment_id": {"$ne": None}}
    )
    log(
        f"\nAssessments: {total} (practice={practice}, drive={drive}); "
        f"templates={templates} (created {templates_created}); "
        f"drives_with_assessment={linked}"
    )
    return {
        "templates": templates,
        "practice_ids": adaptive + standardized,
        "drive_ids": drive_ids,
        "total": total,
        "practice": practice,
        "drive": drive,
        "linked_drives": linked,
    }
