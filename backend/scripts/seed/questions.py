"""Seed the question bank: exactly 500 active questions.

Composition (see the project plan):

====================  =====  ======  ======  ======  ======
section               total  easy    medium  hard    marks
====================  =====  ======  ======  ======  ======
Technical MCQ         300    92      134     74      1/3/5
Aptitude / Verbal     120    34      57      29      1/3/5
Coding                60     12      26      22      1/3/5
Descriptive           20     12      8       0       1/3/5
====================  =====  ======  ======  ======  ======

Every coding question's expected outputs are produced by actually executing
the reference solution through the real ``execute_code`` runner. A coding
question is never inserted with a hand-written answer key.
"""
from __future__ import annotations

import random

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from app.core.skill_taxonomy import canonicalize_skills
from app.models.assessment import DIFFICULTY_MARKS, CodingLanguage, DifficultyLevel, TestCase
from app.services.code_execution_service import execute_code

from scripts.seed import data_aptitude, data_coding, data_descriptive, data_technical
from scripts.seed.context import (
    CATEGORY_NAMES,
    SYNTHETIC,
    category_id,
    ensure_categories,
    now,
    stable_oid,
)

EXPECTED_TOTAL = 500
EXPECTED_DIFFICULTY = {"easy": 150, "medium": 225, "hard": 125}
EXPECTED_TYPES = {"mcq": 420, "coding": 60, "descriptive": 20}


def _technical_documents() -> list[dict]:
    documents: list[dict] = []
    rng = random.Random(20261119)

    for category, facts in data_technical.TECH_FACTS.items():
        terms = [fact[0] for fact in facts]
        definitions = [fact[1] for fact in facts]
        for term, definition, skill, difficulty, explanation in facts:
            other_terms = [t for t in terms if t != term]
            other_definitions = [d for d in definitions if d != definition]
            rng.shuffle(other_terms)
            rng.shuffle(other_definitions)

            # Variant 1: definition -> term
            options = [term, *other_terms[:3]]
            documents.append(
                {
                    "_id": stable_oid(f"q:tech-def:{category}:{term}"),
                    "category_id": str(category_id(category)),
                    "skill_tags": canonicalize_skills([skill]),
                    "difficulty": difficulty,
                    "type": "mcq",
                    "text": f"In {category}, which term matches this description? {definition}",
                    "options": options,
                    "correct_answer": term,
                    "language": None,
                    "starter_code": None,
                    "test_cases": [],
                    "marks": DIFFICULTY_MARKS[DifficultyLevel(difficulty)],
                    "company_tags": [],
                    "created_by": None,  # filled by seed_questions
                    "created_at": now(),
                    "topic": category,
                    "skill": canonicalize_skills([skill])[0] if canonicalize_skills([skill]) else skill,
                    "explanation": explanation,
                    "status": "active",
                    "updated_at": None,
                    **SYNTHETIC,
                }
            )

            # Variant 2: term -> definition
            documents.append(
                {
                    "_id": stable_oid(f"q:tech-term:{category}:{term}"),
                    "category_id": str(category_id(category)),
                    "skill_tags": canonicalize_skills([skill]),
                    "difficulty": difficulty,
                    "type": "mcq",
                    "text": (
                        f"Which statement best describes {term} in the context of {category}?"
                    ),
                    "options": [definition, *other_definitions[:3]],
                    "correct_answer": definition,
                    "language": None,
                    "starter_code": None,
                    "test_cases": [],
                    "marks": DIFFICULTY_MARKS[DifficultyLevel(difficulty)],
                    "company_tags": [],
                    "created_by": None,
                    "created_at": now(),
                    "topic": category,
                    "skill": canonicalize_skills([skill])[0] if canonicalize_skills([skill]) else skill,
                    "explanation": explanation,
                    "status": "active",
                    "updated_at": None,
                    **SYNTHETIC,
                }
            )
    return documents


def _aptitude_documents() -> list[dict]:
    documents: list[dict] = []
    sections = [
        ("Aptitude & Logical Reasoning", data_aptitude.quantitative()),
        ("Aptitude & Logical Reasoning", data_aptitude.logical()),
        ("Verbal Ability", data_aptitude.verbal()),
    ]
    for category, items in sections:
        for index, item in enumerate(items):
            difficulty = item["difficulty"]
            skill_tags = canonicalize_skills([item["skill"]])
            documents.append(
                {
                    "_id": stable_oid(f"q:apt:{category}:{index}:{item['text'][:40]}"),
                    "category_id": str(category_id(category)),
                    "skill_tags": skill_tags,
                    "difficulty": difficulty,
                    "type": "mcq",
                    "text": item["text"],
                    "options": item["options"],
                    "correct_answer": item["answer"],
                    "language": None,
                    "starter_code": None,
                    "test_cases": [],
                    "marks": DIFFICULTY_MARKS[DifficultyLevel(difficulty)],
                    "company_tags": [],
                    "created_by": None,
                    "created_at": now(),
                    "topic": item["topic"],
                    "skill": skill_tags[0] if skill_tags else item["skill"],
                    "explanation": item["explanation"],
                    "status": "active",
                    "updated_at": None,
                    **SYNTHETIC,
                }
            )
    return documents


def _derive_expected_outputs(problem: dict, language: CodingLanguage) -> list[str]:
    """Run the reference solution and return one expected output per input."""
    solution = problem["python"] if language == CodingLanguage.PYTHON else problem["javascript"]
    probe_cases = [
        TestCase(name=f"probe-{index}", input=value, expected_output="", is_hidden=False)
        for index, value in enumerate(problem["inputs"], start=1)
    ]
    summary = execute_code(language, solution, probe_cases)
    if summary.status in {"disabled", "unsupported_language"} or summary.error:
        raise RuntimeError(
            f"Cannot derive expected outputs for {problem['slug']} ({language.value}): "
            f"{summary.status}: {summary.error}"
        )
    outputs: list[str] = []
    for result in summary.results:
        if result.status in {"runtime_error", "timeout", "output_limit_exceeded"}:
            raise RuntimeError(
                f"Reference solution for {problem['slug']} ({language.value}) failed on "
                f"case {result.index}: {result.status} {result.stderr or ''}".strip()
            )
        outputs.append(result.actual_output or "")
    if len(outputs) != len(problem["inputs"]):
        raise RuntimeError(
            f"Expected {len(problem['inputs'])} outputs for {problem['slug']}, got {len(outputs)}"
        )
    return outputs


def _coding_documents(log=print) -> list[dict]:
    documents: list[dict] = []
    for problem in data_coding.PROBLEMS:
        for language in (CodingLanguage.PYTHON, CodingLanguage.JAVASCRIPT):
            outputs = _derive_expected_outputs(problem, language)
            cases = []
            for index, (stdin, expected) in enumerate(zip(problem["inputs"], outputs), start=1):
                cases.append(
                    {
                        "name": "Sample 1" if index == 1 else f"Test {index}",
                        "input": stdin,
                        "expected_output": expected,
                        # Only the first case is a sample; the rest are hidden
                        # from every student-facing API.
                        "is_hidden": index > 1,
                    }
                )
            language_label = "Python 3" if language == CodingLanguage.PYTHON else "JavaScript (Node.js)"
            documents.append(
                {
                    "_id": stable_oid(f"q:coding:{problem['slug']}:{language.value}"),
                    "category_id": str(category_id(problem["category"])),
                    "skill_tags": canonicalize_skills([problem["skill"]]),
                    "difficulty": problem["difficulty"],
                    "type": "coding",
                    "text": (
                        f"{problem['title']}\n\n{problem['prompt']}\n\n"
                        f"Write a {language_label} program that reads from standard input "
                        "and writes the answer to standard output."
                    ),
                    "options": [],
                    "correct_answer": None,
                    "language": language.value,
                    "starter_code": (
                        problem["starter_python"]
                        if language == CodingLanguage.PYTHON
                        else problem["starter_javascript"]
                    ),
                    "test_cases": cases,
                    "marks": DIFFICULTY_MARKS[DifficultyLevel(problem["difficulty"])],
                    "company_tags": [],
                    "created_by": None,
                    "created_at": now(),
                    "topic": problem["category"],
                    "skill": canonicalize_skills([problem["skill"]])[0] if canonicalize_skills([problem["skill"]]) else problem["skill"],
                    "explanation": (
                        f"Reference solution executed successfully against all "
                        f"{len(cases)} test cases."
                    ),
                    "status": "active",
                    "updated_at": None,
                    **SYNTHETIC,
                }
            )
            log(
                f"  CODING {problem['slug']:<28} {language.value:<10} "
                f"{problem['difficulty']:<6} {len(cases)} cases"
            )
    return documents


def _descriptive_documents() -> list[dict]:
    documents: list[dict] = []
    for index, item in enumerate(data_descriptive.descriptive_questions()):
        difficulty = item["difficulty"]
        skill_tags = canonicalize_skills([item["skill"]])
        documents.append(
            {
                "_id": stable_oid(f"q:desc:{index}:{item['text'][:40]}"),
                "category_id": str(category_id(item["category"])),
                "skill_tags": skill_tags,
                "difficulty": difficulty,
                "type": "descriptive",
                "text": item["text"],
                "options": [],
                "correct_answer": None,
                "language": None,
                "starter_code": None,
                "test_cases": [],
                "marks": DIFFICULTY_MARKS[DifficultyLevel(difficulty)],
                "company_tags": [],
                "created_by": None,
                "created_at": now(),
                "topic": item["topic"],
                "skill": skill_tags[0] if skill_tags else item["skill"],
                "explanation": item["explanation"],
                "status": "active",
                "updated_at": None,
                **SYNTHETIC,
            }
        )
    return documents


def build_documents(log=print) -> list[dict]:
    documents = [
        *_technical_documents(),
        *_aptitude_documents(),
        *_coding_documents(log=log),
        *_descriptive_documents(),
    ]
    texts = [doc["text"].strip().lower() for doc in documents]
    if len(set(texts)) != len(texts):
        duplicates = sorted({t for t in texts if texts.count(t) > 1})
        raise RuntimeError(f"Duplicate question text generated: {duplicates[:5]}")
    if len(documents) != EXPECTED_TOTAL:
        raise RuntimeError(f"Expected {EXPECTED_TOTAL} questions, built {len(documents)}")
    return documents


async def seed_questions(db: AsyncIOMotorDatabase, admin_user_id: str, log=print) -> dict:
    categories = await ensure_categories(db)
    missing = [name for name in CATEGORY_NAMES if name not in categories]
    if missing:
        raise RuntimeError(f"Categories missing after ensure_categories: {missing}")

    log("Building question documents (executing coding reference solutions)...")
    documents = build_documents(log=log)
    for doc in documents:
        doc["created_by"] = admin_user_id

    # Replace only this seeder's own questions, so an operator can re-run the
    # step without duplicating rows. A database that still holds unrelated
    # questions must be reset first â€” the project requires exactly 500.
    await db.questions.delete_many({"synthetic_batch": SYNTHETIC["synthetic_batch"]})
    operations = [
        UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True) for doc in documents
    ]
    if operations:
        await db.questions.bulk_write(operations, ordered=False)

    total = await db.questions.count_documents({})
    if total != EXPECTED_TOTAL:
        raise RuntimeError(
            f"Question bank must contain exactly {EXPECTED_TOTAL} questions, found {total}. "
            "Run scripts/reset_db.py before seeding."
        )

    # Verify the required distribution from the database itself.
    difficulty: dict[str, int] = {}
    types: dict[str, int] = {}
    async for row in db.questions.aggregate(
        [{"$group": {"_id": {"difficulty": "$difficulty", "type": "$type"}, "count": {"$sum": 1}}}]
    ):
        difficulty[row["_id"]["difficulty"]] = difficulty.get(row["_id"]["difficulty"], 0) + row["count"]
        types[row["_id"]["type"]] = types.get(row["_id"]["type"], 0) + row["count"]

    if difficulty != EXPECTED_DIFFICULTY:
        raise RuntimeError(f"Difficulty distribution {difficulty} != {EXPECTED_DIFFICULTY}")
    if types != EXPECTED_TYPES:
        raise RuntimeError(f"Type distribution {types} != {EXPECTED_TYPES}")

    per_category = {}
    async for row in db.questions.aggregate(
        [{"$group": {"_id": "$category_id", "count": {"$sum": 1}}}]
    ):
        per_category[row["_id"]] = row["count"]

    log(f"\nQuestion bank: {total} questions")
    log(f"  difficulty: {difficulty}")
    log(f"  types:      {types}")
    for name, oid in categories.items():
        log(f"  {name:<34} {per_category.get(oid, 0):>4}")

    return {
        "total": total,
        "difficulty": difficulty,
        "types": types,
        "categories": categories,
        "per_category": per_category,
    }
