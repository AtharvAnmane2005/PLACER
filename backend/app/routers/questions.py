import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.deps import CurrentUser, require_role
from app.models.assessment import (
    CategoryCreateRequest,
    CategoryResponse,
    QuestionAdminResponse,
    QuestionCreateRequest,
    QuestionInDB,
    QuestionStatsResponse,
    QuestionStatus,
    QuestionUpdateRequest,
)
from app.services.question_import_service import ImportFileError
from app.services.question_service import QuestionError, QuestionService

router = APIRouter()


def _to_admin_response(question: QuestionInDB) -> QuestionAdminResponse:
    return QuestionAdminResponse(
        id=question.id,
        category_id=question.category_id,
        skill_tags=question.skill_tags,
        difficulty=question.difficulty,
        type=question.type,
        text=question.text,
        options=question.options,
        correct_answer=question.correct_answer,
        language=question.language,
        starter_code=question.starter_code,
        test_cases=question.test_cases,
        marks=question.marks,
        company_tags=question.company_tags,
        topic=question.topic,
        skill=question.skill,
        explanation=question.explanation,
        status=question.status,
        updated_at=question.updated_at,
    )


def _http_error(exc: QuestionError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/categories", response_model=CategoryResponse, status_code=201)
async def create_category(
    payload: CategoryCreateRequest,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = QuestionService(db)
    try:
        category = await service.create_category(payload)
    except QuestionError as exc:
        raise _http_error(exc) from exc
    return CategoryResponse(id=category.id, name=category.name, parent_category_id=category.parent_category_id)


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    current_user: CurrentUser = Depends(require_role("admin", "tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    categories = await QuestionService(db).categories.find_many({}, limit=200)
    return [CategoryResponse(id=c.id, name=c.name, parent_category_id=c.parent_category_id) for c in categories]


@router.post("", response_model=QuestionAdminResponse, status_code=201)
async def create_question(
    payload: QuestionCreateRequest,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = QuestionService(db)
    try:
        question = await service.create_question(current_user.id, payload)
    except QuestionError as exc:
        raise _http_error(exc) from exc
    return _to_admin_response(question)


@router.get("", response_model=list[QuestionAdminResponse])
async def list_questions(
    category_id: str | None = None,
    difficulty: str | None = None,
    search: str | None = None,
    question_type: str | None = None,
    topic: str | None = None,
    skill: str | None = None,
    status: str | None = None,
    limit: int = 200,
    current_user: CurrentUser = Depends(require_role("admin", "tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = QuestionService(db)
    if any((search, question_type, topic, skill, status)):
        questions = await service.search(
            search=search,
            category_id=category_id,
            difficulty=difficulty,
            question_type=question_type,
            topic=topic,
            skill=skill,
            status=status,
            limit=min(limit, 1000),
        )
    else:
        questions = await service.questions.find_by_filters(
            category_id=category_id, difficulty=difficulty, limit=min(limit, 1000)
        )
    return [_to_admin_response(q) for q in questions]


@router.get("/stats", response_model=QuestionStatsResponse)
async def question_stats(
    current_user: CurrentUser = Depends(require_role("admin", "tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await QuestionService(db).get_stats()


@router.put("/{question_id}", response_model=QuestionAdminResponse)
async def update_question(
    question_id: str,
    payload: QuestionUpdateRequest,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = QuestionService(db)
    try:
        question = await service.update_question(question_id, payload)
    except QuestionError as exc:
        raise _http_error(exc) from exc
    return _to_admin_response(question)


@router.patch("/{question_id}/status", response_model=QuestionAdminResponse)
async def set_question_status(
    question_id: str,
    status: QuestionStatus,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = QuestionService(db)
    try:
        question = await service.set_status(question_id, status)
    except QuestionError as exc:
        raise _http_error(exc) from exc
    return _to_admin_response(question)


@router.delete("/{question_id}", status_code=204)
async def delete_question(
    question_id: str,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = QuestionService(db)
    try:
        await service.delete_question(question_id)
    except QuestionError as exc:
        raise _http_error(exc) from exc


@router.post("/import", response_model=list[QuestionAdminResponse], status_code=201)
async def import_questions(
    payload: list[QuestionCreateRequest],
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Original JSON import endpoint — preserved for existing clients."""
    service = QuestionService(db)
    try:
        questions = await service.bulk_import(current_user.id, payload)
    except QuestionError as exc:
        raise _http_error(exc) from exc
    return [_to_admin_response(q) for q in questions]


@router.post("/import/preview")
async def preview_import(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Validate an uploaded Excel/CSV file without inserting anything."""
    content = await file.read()
    try:
        preview = await QuestionService(db).preview_import(file.filename or "questions.csv", content)
    except ImportFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return preview


@router.post("/import/commit")
async def commit_import(
    payload: dict,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Insert only reviewed, valid rows. Revalidates everything server-side."""
    rows = payload.get("questions")
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="'questions' must be a list.")
    try:
        parsed = [QuestionCreateRequest(**row) for row in rows]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid question payload: {exc}") from exc
    summary = await QuestionService(db).import_committed(current_user.id, parsed)
    summary["questions"] = [_to_admin_response(q) for q in summary["questions"]]
    return summary


@router.post("/import/error-report")
async def import_error_report(
    payload: dict,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    content = QuestionService.error_report(payload)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="question-import-errors.csv"'},
    )


@router.get("/export/excel")
async def export_excel(
    search: str | None = None,
    category_id: str | None = None,
    difficulty: str | None = None,
    question_type: str | None = None,
    topic: str | None = None,
    skill: str | None = None,
    status: str | None = None,
    ids: str | None = None,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Admin-only workbook export containing real database questions."""
    selected_ids = [part.strip() for part in ids.split(",") if part.strip()] if ids else None
    content = await QuestionService(db).export_excel(
        search=search,
        category_id=category_id,
        difficulty=difficulty,
        question_type=question_type,
        topic=topic,
        skill=skill,
        status=status,
        ids=selected_ids,
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="placer-question-bank.xlsx"'},
    )


@router.get("/export/template")
async def export_template(
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    content = await QuestionService(db).template_workbook()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="placer-question-import-template.xlsx"'},
    )


@router.get("/export", response_model=list[QuestionAdminResponse])
async def export_questions(
    category_id: str | None = None,
    difficulty: str | None = None,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = QuestionService(db)
    questions = await service.export_questions(category_id=category_id, difficulty=difficulty)
    return [_to_admin_response(q) for q in questions]
