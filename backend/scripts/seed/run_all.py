"""Run the complete PLACER seed pipeline against the local database.

Order matters:

1. canonical question categories
2. admin + TPO identities
3. exactly 500 questions (technical, aptitude, coding, descriptive)
4. companies and placement drives
5. templates, practice papers and one standardized paper per drive
6. 50 students, resumes, applications, attempts, decisions, notifications

Every step is idempotent, and the final verification reads the database back
instead of trusting the seeder's return values.

Usage (from ``PLACER/backend``)::

    .venv\\Scripts\\python.exe -m scripts.seed.run_all
    .venv\\Scripts\\python.exe -m scripts.seed.run_all --skip-cohort
    .venv\\Scripts\\python.exe -m scripts.seed.run_all --verify-only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from bson import ObjectId  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.skill_taxonomy import ALIASES, taxonomy_snapshot  # noqa: E402
from app.services.assessment_service import AssessmentService  # noqa: E402

from scripts.seed.assessments import seed_assessments  # noqa: E402
from scripts.seed.cohort import seed_cohort  # noqa: E402
from scripts.seed.companies import seed_companies_and_drives  # noqa: E402
from scripts.seed.context import (  # noqa: E402
    CATEGORY_NAMES,
    SEED_PASSWORD,
    collection_counts,
    ensure_admin,
    ensure_categories,
    ensure_tpo,
    print_counts,
    student_email,
)
from scripts.seed.questions import (  # noqa: E402
    EXPECTED_DIFFICULTY,
    EXPECTED_TOTAL,
    EXPECTED_TYPES,
    seed_questions,
)

EXPECTED_COMPANIES = 14
EXPECTED_DRIVES = 18
EXPECTED_STUDENTS = 50


# ---------------------------------------------------------------------------
# Verification — reads everything back from MongoDB
# ---------------------------------------------------------------------------
async def verify(db) -> dict:
    failures: list[str] = []
    summary: dict = {}

    # --- questions -------------------------------------------------------
    total = await db.questions.count_documents({})
    summary["questions"] = total
    if total != EXPECTED_TOTAL:
        failures.append(f"questions: expected {EXPECTED_TOTAL}, found {total}")

    texts = [doc["text"].strip().lower() for doc in await db.questions.find({}, {"text": 1}).to_list(length=None)]
    if len(set(texts)) != len(texts):
        failures.append(f"questions: {len(texts) - len(set(texts))} duplicate text(s)")

    difficulty: dict[str, int] = {}
    types: dict[str, int] = {}
    async for row in db.questions.aggregate(
        [{"$group": {"_id": {"difficulty": "$difficulty", "type": "$type"}, "count": {"$sum": 1}}}]
    ):
        difficulty[row["_id"]["difficulty"]] = difficulty.get(row["_id"]["difficulty"], 0) + row["count"]
        types[row["_id"]["type"]] = types.get(row["_id"]["type"], 0) + row["count"]
    summary["difficulty"] = difficulty
    summary["types"] = types
    if difficulty != EXPECTED_DIFFICULTY:
        failures.append(f"difficulty distribution {difficulty} != {EXPECTED_DIFFICULTY}")
    if types != EXPECTED_TYPES:
        failures.append(f"type distribution {types} != {EXPECTED_TYPES}")

    categories = await db.question_categories.find({}).to_list(length=None)
    category_names = {str(row["_id"]): row["name"] for row in categories}
    missing_categories = [name for name in CATEGORY_NAMES if name not in category_names.values()]
    if missing_categories:
        failures.append(f"missing canonical categories: {missing_categories}")
    orphan_questions = await db.questions.count_documents(
        {"category_id": {"$nin": list(category_names)}}
    )
    if orphan_questions:
        failures.append(f"{orphan_questions} question(s) point at a missing category")
    per_category: dict[str, int] = {}
    async for row in db.questions.aggregate([{"$group": {"_id": "$category_id", "count": {"$sum": 1}}}]):
        per_category[category_names.get(str(row["_id"]), str(row["_id"]))] = row["count"]
    summary["per_category"] = per_category
    empty_categories = [name for name in CATEGORY_NAMES if per_category.get(name, 0) == 0]
    if empty_categories:
        failures.append(f"categories with no questions: {empty_categories}")

    # --- coding safety ---------------------------------------------------
    coding_questions = await db.questions.find({"type": "coding"}).to_list(length=None)
    summary["coding_questions"] = len(coding_questions)
    forbidden_keys = {
        "solution",
        "reference_solution",
        "python_solution",
        "javascript_solution",
        "solution_code",
    }
    for question in coding_questions:
        label = question.get("text", "")[:60]
        cases = question.get("test_cases") or []
        if len(cases) < 2:
            failures.append(f"coding question has fewer than 2 test cases: {label}")
        visible = [case for case in cases if not case.get("is_hidden", True)]
        hidden = [case for case in cases if case.get("is_hidden", True)]
        if len(visible) != 1:
            failures.append(f"coding question must have exactly 1 visible sample: {label}")
        if not hidden:
            failures.append(f"coding question has no hidden tests: {label}")
        if question.get("correct_answer") is not None:
            failures.append(f"coding question leaks correct_answer: {label}")
        leaked = forbidden_keys & set(question)
        if leaked:
            failures.append(f"coding question stores reference solution keys {leaked}: {label}")

    descriptive = await db.questions.count_documents({"type": "descriptive"})
    summary["descriptive_questions"] = descriptive
    if descriptive != 20:
        failures.append(f"descriptive: expected 20, found {descriptive}")
    if await db.questions.count_documents(
        {"type": "descriptive", "correct_answer": {"$ne": None}}
    ):
        failures.append("descriptive questions must not have a correct_answer")

    # --- companies / drives ---------------------------------------------
    companies = await db.companies.count_documents({})
    drives = await db.placement_drives.find({}).to_list(length=None)
    summary["companies"] = companies
    summary["drives"] = len(drives)
    if companies < EXPECTED_COMPANIES:
        failures.append(f"companies: expected at least {EXPECTED_COMPANIES}, found {companies}")
    if len(drives) < EXPECTED_DRIVES:
        failures.append(f"drives: expected at least {EXPECTED_DRIVES}, found {len(drives)}")
    for drive in drives:
        label = f"{drive.get('company_id')}/{drive.get('job_title')}"
        if not drive.get("jd_text"):
            failures.append(f"drive has no jd_text: {label}")
        if not drive.get("required_skills"):
            failures.append(f"drive has no required_skills: {label}")
        if not drive.get("required_assessment_id"):
            failures.append(f"drive has no assessment: {label}")

    # --- assessments -----------------------------------------------------
    assessments = await db.assessments.find({}).to_list(length=None)
    summary["assessments"] = len(assessments)
    summary["templates"] = await db.assessment_templates.count_documents({})
    drive_assessments = [a for a in assessments if a.get("type") == "drive"]
    coding_assessments = 0
    for assessment in drive_assessments:
        label = assessment.get("title")
        if assessment.get("format") != "standardized":
            failures.append(f"drive assessment is not standardized: {label}")
        if len(assessment.get("question_ids") or []) != 20:
            failures.append(f"drive assessment does not have 20 questions: {label}")
        coding_ids = await db.questions.count_documents(
            {
                "_id": {
                    "$in": [
                        ObjectId(question_id)
                        for question_id in (assessment.get("question_ids") or [])
                        if ObjectId.is_valid(question_id)
                    ]
                },
                "type": "coding",
            }
        )
        if coding_ids:
            coding_assessments += 1
        else:
            failures.append(f"drive assessment has no coding question: {label}")
    summary["drive_assessments"] = len(drive_assessments)
    summary["drive_assessments_with_coding"] = coding_assessments

    # A student-facing view must expose only visible sample tests and never
    # the answer key. This exercises the real projection the API uses.
    sample = next((a for a in drive_assessments if a.get("question_ids")), None)
    if sample:
        service = AssessmentService(db)
        views = await service.get_fixed_questions(str(sample["_id"]))
        coding_views = [view for view in views if view.type.value == "coding"]
        if not coding_views:
            failures.append("student view did not include the assessment's coding question")
        for view in coding_views:
            if any(case.is_hidden for case in view.visible_test_cases):
                failures.append("student view leaked a hidden coding test case")
            if hasattr(view, "correct_answer"):
                failures.append("student view exposes correct_answer")

    # --- students / activity --------------------------------------------
    student_users = await db.users.count_documents({"role": "student"})
    students = await db.students.count_documents({})
    resumes = await db.resumes.count_documents({"is_active": True})
    summary.update(
        {
            "student_users": student_users,
            "students": students,
            "active_resumes": resumes,
            "applications": await db.applications.count_documents({}),
            "attempts": await db.assessment_attempts.count_documents({}),
            "submitted_attempts": await db.assessment_attempts.count_documents(
                {"status": "submitted"}
            ),
            "knowledge_states": await db.knowledge_states.count_documents({}),
            "notifications": await db.notifications.count_documents({}),
        }
    )
    if student_users < EXPECTED_STUDENTS:
        failures.append(f"student users: expected {EXPECTED_STUDENTS}, found {student_users}")
    if students < EXPECTED_STUDENTS:
        failures.append(f"student profiles: expected {EXPECTED_STUDENTS}, found {students}")
    if resumes < EXPECTED_STUDENTS:
        failures.append(f"active resumes: expected {EXPECTED_STUDENTS}, found {resumes}")
    missing_emails = [
        student_email(index)
        for index in range(1, EXPECTED_STUDENTS + 1)
        if not await db.users.find_one({"email": student_email(index), "role": "student"})
    ]
    if missing_emails:
        failures.append(f"missing seeded student logins: {missing_emails[:5]}")
    if summary["applications"] <= 0:
        failures.append("no applications were seeded")
    if summary["submitted_attempts"] <= 0:
        failures.append("no submitted assessment attempts were seeded")

    coding_answers = await db.assessment_attempts.count_documents(
        {"answers": {"$elemMatch": {"question_type": "coding", "code_result": {"$ne": None}}}}
    )
    passed_coding = await db.assessment_attempts.count_documents(
        {
            "answers": {
                "$elemMatch": {
                    "question_type": "coding",
                    "is_correct": True,
                    "code_result.all_passed": True,
                }
            }
        }
    )
    summary["coding_answers"] = coding_answers
    summary["passed_coding_answers"] = passed_coding
    if coding_answers <= 0:
        failures.append("no coding answer was graded through the execution runner")
    if passed_coding <= 0:
        failures.append("no coding answer passed its hidden tests")

    snapshot = taxonomy_snapshot()
    summary["taxonomy"] = {
        "skills": snapshot["total_skills"],
        "aliases": len(ALIASES),
        "domains": snapshot["total_domains"],
    }
    summary["counts"] = await collection_counts(db)
    summary["failures"] = failures
    return summary


# ---------------------------------------------------------------------------
# Credentials guide (git-ignored directory)
# ---------------------------------------------------------------------------
def write_credentials() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = Path("db_backups") / f"seed_credentials_{stamp}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "PLACER local development credentials",
        "===================================",
        f"Database : placer_db (localhost only)",
        f"Password : {SEED_PASSWORD}",
        "",
        "Admin",
        "  admin@placer.edu",
        "",
        "TPO",
        "  tpo@placer.edu",
        "",
        "Students (all use the same password)",
        *[f"  {student_email(index)}" for index in range(1, EXPECTED_STUDENTS + 1)],
        "",
        "This file lives under db_backups/, which is git-ignored. Do not commit it.",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]
    try:
        await client.admin.command("ping")
        if args.verify_only:
            summary = await verify(db)
            print(json.dumps(summary, indent=2, default=str))
            return 0 if not summary["failures"] else 1

        print("Categories:")
        await ensure_categories(db)
        admin_user, _admin_profile = await ensure_admin(db)
        tpo_user, _tpo_profile = await ensure_tpo(db)
        print(f"  admin={admin_user.email}  tpo={tpo_user.email}")

        print("\nQuestion bank:")
        questions = await seed_questions(db, admin_user.id)

        print("\nCompanies and drives:")
        drives = await seed_companies_and_drives(db, tpo_user.id)
        print(f"  {len(drives)} drive(s) available")

        print("\nAssessments:")
        assessments = await seed_assessments(db, admin_user.id, tpo_user.id)

        if args.skip_cohort:
            print("\nSkipping student cohort (--skip-cohort).")
            cohort = {}
        else:
            print("\nStudent cohort:")
            cohort = await seed_cohort(db, tpo_user.id)

        print("\nVerification:")
        summary = await verify(db)
        summary["seed_questions"] = {
            "total": questions["total"],
            "difficulty": questions["difficulty"],
            "types": questions["types"],
        }
        summary["seed_assessments"] = assessments
        summary["seed_cohort"] = cohort

        await print_counts(db)
        print("\nVerification result")
        print("-" * 40)
        if summary["failures"]:
            for failure in summary["failures"]:
                print(f"  FAIL {failure}")
        else:
            print("  PASS  all checks succeeded")

        if not args.no_credentials:
            path = write_credentials()
            print(f"\nCredentials guide: {path}")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report = Path("db_backups") / f"seed_summary_{stamp}.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"Seed summary:     {report}")

        return 0 if not summary["failures"] else 1
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the complete local PLACER database.")
    parser.add_argument("--skip-cohort", action="store_true", help="Skip students/attempts.")
    parser.add_argument("--verify-only", action="store_true", help="Only run verification.")
    parser.add_argument(
        "--no-credentials",
        action="store_true",
        help="Do not write the local credentials guide.",
    )
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
