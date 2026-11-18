"""Admin-facing question bank management.

The original JSON import/export endpoints are preserved unchanged for
backwards compatibility. This service additionally supports validated
Excel/CSV preview-and-commit imports and styled Excel exports.
"""
from __future__ import annotations

import json
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.models.assessment import (
    DIFFICULTY_MARKS,
    PLACEMENT_SECTION_SIZE,
    PLACEMENT_SECTIONS,
    CategoryCreateRequest,
    CodingLanguage,
    DifficultyLevel,
    QuestionCategoryInDB,
    QuestionCreateRequest,
    QuestionInDB,
    QuestionStatsResponse,
    QuestionStatus,
    QuestionType,
    QuestionUpdateRequest,
    TestCase,
)
from app.repositories.question_repository import QuestionCategoryRepository, QuestionRepository
from app.services.question_import_service import (
    ImportFileError,
    build_error_report,
    build_export_workbook,
    build_template_workbook,
    coerce_row,
    parse_question_file,
)

MULTIPLE_SELECT_SEPARATOR = "|"


class QuestionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def normalize_correct_answer(question_type: QuestionType, answer: str | None) -> str | None:
    if answer is None:
        return None
    value = answer.strip()
    if question_type == QuestionType.MULTIPLE_SELECT:
        if value.startswith("["):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    value = MULTIPLE_SELECT_SEPARATOR.join(str(v).strip() for v in parsed if str(v).strip())
            except (ValueError, TypeError):
                pass
        parts = [part.strip() for part in value.split(MULTIPLE_SELECT_SEPARATOR) if part.strip()]
        # Deduplicate while preserving the administrator's order.
        return MULTIPLE_SELECT_SEPARATOR.join(dict.fromkeys(parts)) if parts else None
    return value or None


class QuestionService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.categories = QuestionCategoryRepository(db)
        self.questions = QuestionRepository(db)

    async def create_category(self, payload: CategoryCreateRequest) -> QuestionCategoryInDB:
        name = payload.name.strip()
        if not name:
            raise QuestionError("Category name is required.")
        existing = await self.categories.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
        if existing:
            raise QuestionError("A category with this name already exists.", 409)
        return await self.categories.create({"name": name, "parent_category_id": payload.parent_category_id})

    @staticmethod
    def _validate_question_payload(
        question_type: QuestionType,
        options: list[str],
        correct_answer: str | None,
        language: CodingLanguage | None = None,
        test_cases: list[TestCase] | None = None,
        starter_code: str | None = None,
        text: str = "",
    ) -> None:
        if question_type == QuestionType.MCQ:
            if len(options) < 2:
                raise QuestionError("MCQ questions need at least 2 options.")
            if not correct_answer:
                raise QuestionError("MCQ questions require a correct_answer.")
            if correct_answer not in options:
                raise QuestionError("correct_answer must be one of the provided options.")
        elif question_type == QuestionType.MULTIPLE_SELECT:
            if len(options) < 2:
                raise QuestionError("Multiple-select questions need at least 2 options.")
            normalized = normalize_correct_answer(question_type, correct_answer)
            if not normalized:
                raise QuestionError("Multiple-select questions require at least one correct answer.")
            invalid = [part for part in normalized.split(MULTIPLE_SELECT_SEPARATOR) if part not in options]
            if invalid:
                raise QuestionError("Every correct answer must match one of the provided options.")
        elif question_type == QuestionType.TRUE_FALSE:
            answer = (correct_answer or "").strip().lower()
            if answer not in {"true", "false"}:
                raise QuestionError("True/False questions require 'True' or 'False' as the correct answer.")
        elif question_type == QuestionType.CODING:
            if language is None:
                raise QuestionError("Coding questions require a language.")
            cases = test_cases or []
            # Backward compatibility: questions created before test cases
            # existed used correct_answer as a single empty-input expected
            # output. Keep accepting that shape so old data and imports work.
            if not cases and not correct_answer:
                raise QuestionError(
                    "Coding questions need at least one test case "
                    "(input + expected output), or a legacy expected-output answer."
                )
            settings = get_settings()
            if len(cases) > settings.CODE_EXECUTION_MAX_TEST_CASES:
                raise QuestionError(
                    f"A coding question can have at most {settings.CODE_EXECUTION_MAX_TEST_CASES} test cases."
                )
            for index, case in enumerate(cases, start=1):
                if len(case.input.encode("utf-8")) > 10000:
                    raise QuestionError(f"Test case {index} input is too large (limit 10,000 bytes).")
                if len(case.expected_output.encode("utf-8")) > 10000:
                    raise QuestionError(f"Test case {index} expected output is too large (limit 10,000 bytes).")
            if starter_code and len(starter_code.encode("utf-8")) > settings.CODE_EXECUTION_MAX_CODE_BYTES:
                raise QuestionError("Starter code is too large.")
        elif question_type == QuestionType.DESCRIPTIVE:
            if not correct_answer:
                pass  # descriptive answers are intentionally ungraded
        if not text.strip():
            raise QuestionError("Question text is required.")

    @staticmethod
    def _category_names(categories: list[QuestionCategoryInDB]) -> dict[str, str]:
        return {c.id: c.name for c in categories}

    async def _resolve_category(self, value: str) -> str:
        from bson import ObjectId

        if ObjectId.is_valid(value):
            category = await self.categories.get_by_id(value)
            if category:
                return value
        category = await self.categories.find_one({"name": {"$regex": f"^{value}$", "$options": "i"}})
        if not category:
            raise QuestionError(f"Category not found: {value}", 404)
        return category.id

    async def _build_document(
        self, admin_user_id: str, payload: QuestionCreateRequest, *, check_duplicate: bool = True
    ) -> dict:
        category_id = await self._resolve_category(payload.category_id)
        is_coding = payload.type == QuestionType.CODING
        normalized_answer = normalize_correct_answer(payload.type, payload.correct_answer)
        options = list(payload.options)
        if payload.type == QuestionType.TRUE_FALSE and not options:
            options = ["True", "False"]
        self._validate_question_payload(
            payload.type,
            options,
            normalized_answer,
            language=payload.language if is_coding else None,
            test_cases=payload.test_cases if is_coding else None,
            starter_code=payload.starter_code if is_coding else None,
            text=payload.text,
        )
        if check_duplicate:
            duplicate = await self.questions.find_duplicate(payload.text)
            if duplicate:
                raise QuestionError(
                    f"A question with the same text already exists ({duplicate.id}).", 409
                )
        marks = payload.marks if payload.marks is not None else DIFFICULTY_MARKS[payload.difficulty]
        return {
            "category_id": category_id,
            "skill_tags": payload.skill_tags,
            "difficulty": payload.difficulty.value,
            "type": payload.type.value,
            "text": payload.text.strip(),
            "options": options,
            "correct_answer": normalized_answer if not is_coding else payload.correct_answer,
            "language": payload.language.value if is_coding and payload.language else None,
            "starter_code": payload.starter_code if is_coding else None,
            "test_cases": [case.model_dump() for case in payload.test_cases] if is_coding else [],
            "marks": marks,
            "company_tags": payload.company_tags,
            "created_by": admin_user_id,
            "created_at": datetime.utcnow(),
            "topic": payload.topic,
            "skill": payload.skill or (payload.skill_tags[0] if payload.skill_tags else None),
            "explanation": payload.explanation,
            "status": payload.status.value,
            "updated_at": None,
        }

    async def create_question(self, admin_user_id: str, payload: QuestionCreateRequest) -> QuestionInDB:
        document = await self._build_document(admin_user_id, payload)
        return await self.questions.create(document)

    async def update_question(self, question_id: str, payload: QuestionUpdateRequest) -> QuestionInDB:
        existing = await self.questions.get_by_id(question_id)
        if not existing:
            raise QuestionError("Question not found.", 404)

        update_data = payload.model_dump(exclude_unset=True)

        new_type = payload.type or existing.type
        new_options = payload.options if payload.options is not None else existing.options
        answer_raw = payload.correct_answer if "correct_answer" in update_data else existing.correct_answer
        new_answer = normalize_correct_answer(new_type, answer_raw)
        new_language = payload.language if "language" in update_data else existing.language
        new_test_cases = payload.test_cases if "test_cases" in update_data else existing.test_cases
        new_starter_code = payload.starter_code if "starter_code" in update_data else existing.starter_code
        new_text = payload.text if payload.text is not None else existing.text

        is_coding = new_type == QuestionType.CODING
        self._validate_question_payload(
            new_type,
            new_options,
            new_answer,
            language=new_language if is_coding else None,
            test_cases=new_test_cases if is_coding else None,
            starter_code=new_starter_code if is_coding else None,
            text=new_text,
        )
        if payload.text and payload.text.strip() != existing.text.strip():
            duplicate = await self.questions.find_duplicate(payload.text, exclude_id=question_id)
            if duplicate:
                raise QuestionError(f"A question with the same text already exists ({duplicate.id}).", 409)

        if "difficulty" in update_data:
            update_data["difficulty"] = payload.difficulty.value
            if "marks" not in update_data or update_data["marks"] is None:
                update_data["marks"] = DIFFICULTY_MARKS[payload.difficulty]
        if "type" in update_data:
            update_data["type"] = payload.type.value
        if "language" in update_data:
            update_data["language"] = payload.language.value if payload.language else None
        if "test_cases" in update_data:
            update_data["test_cases"] = [case.model_dump() for case in (payload.test_cases or [])]
        if "correct_answer" in update_data:
            update_data["correct_answer"] = new_answer if not is_coding else answer_raw
        if "status" in update_data and payload.status is not None:
            update_data["status"] = payload.status.value
        if "marks" in update_data and update_data["marks"] is None:
            update_data.pop("marks")
        update_data["updated_at"] = datetime.utcnow()

        # Switching away from coding must not leave coding-only fields behind.
        if not is_coding:
            update_data["language"] = None
            update_data["starter_code"] = None
            update_data["test_cases"] = []

        updated = await self.questions.update_by_id(question_id, update_data)
        if not updated:
            raise QuestionError("Question not found.", 404)
        return updated

    async def delete_question(self, question_id: str) -> None:
        deleted = await self.questions.delete_by_id(question_id)
        if not deleted:
            raise QuestionError("Question not found.", 404)

    async def set_status(self, question_id: str, status: QuestionStatus) -> QuestionInDB:
        updated = await self.questions.update_by_id(
            question_id, {"status": status.value, "updated_at": datetime.utcnow()}
        )
        if not updated:
            raise QuestionError("Question not found.", 404)
        return updated

    async def get_stats(self) -> QuestionStatsResponse:
        return QuestionStatsResponse(**(await self.questions.stats()))

    async def search(self, **filters) -> list[QuestionInDB]:
        return await self.questions.search(**filters)

    async def bulk_import(self, admin_user_id: str, questions: list[QuestionCreateRequest]) -> list[QuestionInDB]:
        # Kept for the original JSON endpoint: validate everything before
        # inserting anything so a later bad row cannot leave a partial batch.
        documents = [await self._build_document(admin_user_id, q) for q in questions]
        seen: set[str] = set()
        for document in documents:
            key = " ".join(document["text"].lower().split())
            if key in seen:
                raise QuestionError(f"Duplicate question in import: {document['text'][:80]}", 409)
            seen.add(key)
        if not documents:
            return []
        return await self.questions.bulk_insert(documents)

    async def import_committed(
        self, admin_user_id: str, questions: list[QuestionCreateRequest]
    ) -> dict:
        """Insert only fully valid, reviewed rows; return a detailed summary."""
        created: list[QuestionInDB] = []
        duplicates: list[dict] = []
        failed: list[dict] = []
        seen: set[str] = set()
        documents: list[dict] = []
        for index, payload in enumerate(questions, start=1):
            key = " ".join(payload.text.strip().lower().split())
            try:
                if key in seen or await self.questions.find_duplicate(payload.text):
                    duplicates.append({"row": index, "text": payload.text})
                    continue
                documents.append(await self._build_document(admin_user_id, payload))
                seen.add(key)
            except QuestionError as exc:
                failed.append({"row": index, "text": payload.text, "error": exc.message})
        if documents:
            created = await self.questions.bulk_insert(documents)
        return {
            "total_rows": len(questions),
            "imported": len(created),
            "duplicates": len(duplicates),
            "invalid": len(failed),
            "failed": len(failed),
            "duplicate_rows": duplicates,
            "failed_rows": failed,
            "questions": created,
        }

    async def preview_import(self, filename: str, content: bytes) -> dict:
        sheet = parse_question_file(filename, content)
        categories = await self.categories.find_many({}, limit=500)
        category_by_name = {c.name.lower(): c.id for c in categories}
        category_ids = {c.id for c in categories}
        seen: dict[str, int] = {}
        rows = []
        invalid = 0
        duplicate_count = 0
        all_errors: list[dict] = []

        for row_number, values in enumerate(sheet.rows, start=2):
            raw = coerce_row(values, sheet)
            errors: list[dict] = []
            category_value = raw.get("category_id", "")
            if category_value in category_ids:
                raw["category_id"] = category_value
            elif category_value.lower() in category_by_name:
                raw["category_id"] = category_by_name[category_value.lower()]
            else:
                errors.append({"row": row_number, "field": "category", "message": f"Unknown category: {category_value}"})

            try:
                difficulty = DifficultyLevel(raw.get("difficulty", ""))
            except ValueError:
                errors.append({"row": row_number, "field": "difficulty", "message": "Must be easy, medium or hard."})
                difficulty = None

            try:
                question_type = QuestionType(raw.get("type", ""))
            except ValueError:
                errors.append(
                    {
                        "row": row_number,
                        "field": "question_type",
                        "message": "Must be mcq, multiple_select, true_false, coding or descriptive.",
                    }
                )
                question_type = None

            marks_raw = raw.pop("marks", None)
            marks_value = None
            if marks_raw not in (None, ""):
                try:
                    marks_value = int(marks_raw)
                    if marks_value < 0:
                        raise ValueError
                except (ValueError, TypeError):
                    errors.append({"row": row_number, "field": "marks", "message": "Marks must be a non-negative integer."})

            question = None
            if not errors:
                try:
                    payload_values = dict(raw)
                    payload_values.pop("difficulty", None)
                    payload_values.pop("type", None)
                    question = QuestionCreateRequest(
                        **payload_values,
                        difficulty=difficulty,
                        type=question_type,
                        marks=marks_value,
                    )
                    # Full service validation (options, answers, duplicates).
                    await self._build_document("preview", question)
                except QuestionError as exc:
                    errors.append({"row": row_number, "field": "question", "message": exc.message})
                    if "already exists" in exc.message:
                        duplicate_count += 1
                except Exception as exc:  # pragma: no cover - defensive
                    errors.append({"row": row_number, "field": "question", "message": str(exc)})

            key = " ".join(str(raw.get("text", "")).strip().lower().split())
            if key and key in seen:
                errors.append(
                    {"row": row_number, "field": "text", "message": f"Duplicate of row {seen[key]} in this file."}
                )
                duplicate_count += 1
            elif key:
                seen[key] = row_number

            all_errors.extend(errors)
            if errors:
                invalid += 1
            rows.append(
                {
                    "row": row_number,
                    # Retain the original text so the downloadable error report
                    # can identify invalid rows even when no valid payload was
                    # built for them.
                    "raw_text": str(raw.get("text", "")),
                    "question": question if not errors else None,
                    "errors": errors,
                }
            )

        return {
            "filename": filename,
            "detected_columns": sheet.mapping,
            "total_rows": sheet.raw_row_count,
            "valid_rows": sheet.raw_row_count - invalid,
            "invalid_rows": invalid,
            "duplicate_rows": duplicate_count,
            "rows": rows,
            "errors": all_errors,
        }

    async def export_excel(
        self,
        *,
        search: str | None = None,
        category_id: str | None = None,
        difficulty: str | None = None,
        question_type: str | None = None,
        topic: str | None = None,
        skill: str | None = None,
        status: str | None = None,
        ids: list[str] | None = None,
    ) -> bytes:
        questions = await self.questions.search(
            search=search,
            category_id=category_id,
            difficulty=difficulty,
            question_type=question_type,
            topic=topic,
            skill=skill,
            status=status or "all",
            ids=ids,
            limit=100000,
        )
        categories = await self.categories.find_many({}, limit=500)
        return build_export_workbook(questions, self._category_names(categories))

    async def export_questions(
        self, category_id: str | None = None, difficulty: str | None = None
    ) -> list[QuestionInDB]:
        return await self.questions.find_by_filters(category_id=category_id, difficulty=difficulty, limit=1000)

    async def template_workbook(self) -> bytes:
        """Blank, import-ready workbook enriched with live categories and sections."""
        categories = await self.categories.find_many({}, limit=500)
        names = [category.name for category in categories]
        sections = [(name, PLACEMENT_SECTION_SIZE) for name in PLACEMENT_SECTIONS]
        return build_template_workbook(names, sections)

    @staticmethod
    def error_report(preview: dict) -> bytes:
        return build_error_report(preview)
