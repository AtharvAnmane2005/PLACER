from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.deps import CurrentUser, get_current_user, require_role
from app.models.assessment import (
    DIFFICULTY_MARKS,
    AssessmentCreateRequest,
    AssessmentFormat,
    AssessmentInDB,
    AssessmentResponse,
    AssessmentTemplateResponse,
    AssessmentTemplateUpsertRequest,
    AssessmentType,
    AttemptAnswerDetail,
    AttemptQuestionsResponse,
    AttemptResultResponse,
    AttemptStatus,
    CodeRunSummary,
    FinishAttemptRequest,
    FinishAttemptResponse,
    KnowledgeStateResponse,
    PlacementEligibilityResponse,
    PlacementGenerationRequest,
    PlacementGenerationResponse,
    PlacementParticipationResponse,
    PlacementRevisionRequest,
    RunCodeRequest,
    RunCodeResponse,
    StartAttemptRequest,
    StartAttemptResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    TemplatePresetResponse,
    TemplateStatus,
    ViolationReportRequest,
    ViolationReportResponse,
)
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.profile_repositories import StudentRepository
from app.repositories.question_repository import QuestionRepository
from app.services.assessment_service import AssessmentError, AssessmentService, to_student_view
from app.services.knowledge_tracing_service import KnowledgeTracingService
from app.services.placement_assessment_service import PlacementAssessmentService, PlacementGenerationError
from app.services.template_service import TemplateError, TemplateService

router = APIRouter()


def _to_assessment_response(assessment: AssessmentInDB) -> AssessmentResponse:
    """Single mapper used by create/list/generate so new fields stay consistent."""
    return AssessmentResponse(
        id=assessment.id,
        title=assessment.title,
        category_ids=assessment.category_ids,
        question_pool_size=assessment.question_pool_size,
        time_limit_sec=assessment.time_limit_sec,
        anti_cheat_config=assessment.anti_cheat_config,
        type=assessment.type,
        drive_id=assessment.drive_id,
        format=assessment.format,
        status=assessment.status,
        question_count=len(assessment.question_ids),
        total_marks=assessment.total_marks,
        passing_marks=assessment.passing_marks,
        negative_marks=assessment.negative_marks,
        instructions=assessment.instructions,
        allow_retake=assessment.allow_retake,
        template_id=assessment.template_id,
        sections=assessment.sections,
    )


# ---------------------------------------------------------------------------
# Reusable assessment templates (admin only)
# ---------------------------------------------------------------------------
@router.get("/templates/presets", response_model=list[TemplatePresetResponse])
async def template_presets(
    current_user: CurrentUser = Depends(require_role("admin")),
):
    return TemplateService.presets()


@router.get("/templates", response_model=list[AssessmentTemplateResponse])
async def list_templates(
    status: TemplateStatus | None = None,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    templates = await TemplateService(db).list(status=status.value if status else None)
    return [TemplateService.to_response(t) for t in templates]


@router.post("/templates", response_model=AssessmentTemplateResponse, status_code=201)
async def create_template(
    payload: AssessmentTemplateUpsertRequest,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        template = await TemplateService(db).create(payload, current_user.id)
    except TemplateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return TemplateService.to_response(template)


@router.get("/templates/{template_id}", response_model=AssessmentTemplateResponse)
async def get_template(
    template_id: str,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        template = await TemplateService(db).get(template_id)
    except TemplateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return TemplateService.to_response(template)


@router.put("/templates/{template_id}", response_model=AssessmentTemplateResponse)
async def update_template(
    template_id: str,
    payload: AssessmentTemplateUpsertRequest,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        template = await TemplateService(db).update(template_id, payload)
    except TemplateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return TemplateService.to_response(template)


@router.post("/templates/{template_id}/duplicate", response_model=AssessmentTemplateResponse, status_code=201)
async def duplicate_template(
    template_id: str,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        template = await TemplateService(db).duplicate(template_id, current_user.id)
    except TemplateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return TemplateService.to_response(template)


@router.patch("/templates/{template_id}/status", response_model=AssessmentTemplateResponse)
async def set_template_status(
    template_id: str,
    status: TemplateStatus,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        template = await TemplateService(db).set_status(template_id, status)
    except TemplateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return TemplateService.to_response(template)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        await TemplateService(db).delete(template_id)
    except TemplateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ---------------------------------------------------------------------------
# Standardized placement-drive assessments (admin only)
# ---------------------------------------------------------------------------
@router.post("/placement/eligibility", response_model=PlacementEligibilityResponse)
async def placement_eligibility(
    payload: PlacementGenerationRequest,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        return await PlacementAssessmentService(db).eligibility(payload.drive_id, payload)
    except PlacementGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/placement/generate", response_model=PlacementGenerationResponse, status_code=201)
async def generate_placement_assessment(
    payload: PlacementGenerationRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    client_ip = request.client.host if request.client else None
    try:
        return await PlacementAssessmentService(db).generate(payload, current_user.id, client_ip)
    except PlacementGenerationError as exc:
        detail = {"message": exc.message, "deficits": exc.deficits}
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc


@router.post("/placement/{assessment_id}/revise", response_model=PlacementGenerationResponse)
async def revise_placement_assessment(
    assessment_id: str,
    payload: PlacementRevisionRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    client_ip = request.client.host if request.client else None
    try:
        return await PlacementAssessmentService(db).revise(
            assessment_id, payload, current_user.id, client_ip
        )
    except PlacementGenerationError as exc:
        detail = {"message": exc.message, "deficits": exc.deficits}
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc


@router.get("/placement/{drive_id}/participation", response_model=PlacementParticipationResponse)
async def placement_participation(
    drive_id: str,
    assessment_id: str = Query(...),
    current_user: CurrentUser = Depends(require_role("admin", "tpo")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        return await PlacementAssessmentService(db).participation(drive_id, assessment_id)
    except PlacementGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ---------------------------------------------------------------------------
# General assessments (adaptive) and attempt flow
# ---------------------------------------------------------------------------
@router.post("", response_model=AssessmentResponse, status_code=201)
async def create_assessment(
    payload: AssessmentCreateRequest,
    current_user: CurrentUser = Depends(require_role("admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if payload.format == AssessmentFormat.STANDARDIZED:
        raise HTTPException(
            status_code=400,
            detail="Standardized assessments must be generated through the placement generation endpoint.",
        )
    anti_cheat_config = {
        "max_violations": payload.max_violations,
        "require_fullscreen": payload.require_fullscreen,
    }
    assessment = await AssessmentRepository(db).create(
        {
            "title": payload.title,
            "category_ids": payload.category_ids,
            "question_pool_size": payload.question_pool_size,
            "time_limit_sec": payload.time_limit_sec,
            "anti_cheat_config": anti_cheat_config,
            "type": payload.type.value,
            "created_by": current_user.id,
            "format": AssessmentFormat.ADAPTIVE.value,
            "status": "published",
            "instructions": payload.instructions,
            "allow_retake": payload.allow_retake,
            "negative_marks": payload.negative_marks,
        }
    )
    return _to_assessment_response(assessment)


@router.get("", response_model=list[AssessmentResponse])
async def list_assessments(
    type_filter: AssessmentType | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    query: dict = {}
    if type_filter:
        query["type"] = type_filter.value
    assessments = await AssessmentRepository(db).find_many(query, limit=200)
    return [_to_assessment_response(a) for a in assessments]


@router.get("/knowledge-states/me", response_model=list[KnowledgeStateResponse])
async def my_knowledge_states(
    current_user: CurrentUser = Depends(require_role("student")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    student = await StudentRepository(db).get_by_user_id(current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")

    kts = KnowledgeTracingService(db)
    states = await kts.knowledge_states.get_all_for_student(student.id)
    return [
        KnowledgeStateResponse(
            skill_tag=s.skill_tag,
            mastery_pct=s.mastery_pct,
            confidence=s.confidence,
            attempts_count=s.attempts_count,
        )
        for s in states
    ]


@router.get("/knowledge-states/{student_id}", response_model=list[KnowledgeStateResponse])
async def student_knowledge_states(
    student_id: str,
    current_user: CurrentUser = Depends(require_role("tpo", "admin")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if current_user.role == "tpo":
        from app.repositories.application_repository import ApplicationRepository
        from app.repositories.drive_repository import PlacementDriveRepository
        from app.repositories.profile_repositories import TPORepository

        tpo = await TPORepository(db).get_by_user_id(current_user.id)
        if not tpo:
            raise HTTPException(status_code=403, detail="TPO profile not found.")
        # Check if this student has applied to any drive owned by this TPO
        drives = await PlacementDriveRepository(db).find_many({"created_by": tpo.id}, limit=500)
        drive_ids = [d.id for d in drives]
        app_match = await ApplicationRepository(db).find_one({"student_id": student_id, "drive_id": {"$in": drive_ids}})
        if not app_match:
            raise HTTPException(status_code=403, detail="You do not have permission to view this student's knowledge states.")

    kts = KnowledgeTracingService(db)
    states = await kts.knowledge_states.get_all_for_student(student_id)
    return [
        KnowledgeStateResponse(
            skill_tag=s.skill_tag,
            mastery_pct=s.mastery_pct,
            confidence=s.confidence,
            attempts_count=s.attempts_count,
        )
        for s in states
    ]


@router.post("/{assessment_id}/start", response_model=StartAttemptResponse, status_code=201)
async def start_assessment(
    assessment_id: str,
    payload: StartAttemptRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_role("student")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = AssessmentService(db)
    client_ip = request.client.host if request.client else None
    try:
        attempt, first_question = await service.start_attempt(
            current_user.id,
            assessment_id,
            fingerprint_hash=payload.fingerprint_hash,
            ip_address=client_ip,
            application_id=payload.application_id,
        )
    except AssessmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    assessment = await service.assessments.get_by_id(assessment_id)
    elapsed_sec = max(0.0, (datetime.utcnow() - attempt.started_at).total_seconds())
    time_remaining_sec = max(0, int(assessment.time_limit_sec - elapsed_sec))
    standardized = service._is_standardized(assessment)
    questions = await service.get_fixed_questions(assessment_id) if standardized else []
    return StartAttemptResponse(
        attempt_id=attempt.id,
        session_token=attempt.session_token,
        time_limit_sec=assessment.time_limit_sec,
        time_remaining_sec=time_remaining_sec,
        anti_cheat_config=assessment.anti_cheat_config,
        next_question=to_student_view(first_question) if first_question else None,
        questions=questions,
        answered_question_ids=service.answered_ids(attempt) if standardized else [],
        total_questions=len(assessment.question_ids) if standardized else 0,
        format=assessment.format,
        instructions=assessment.instructions if standardized else "",
        total_marks=assessment.total_marks if standardized else 0,
    )


@router.get("/attempts/{attempt_id}/questions", response_model=AttemptQuestionsResponse)
async def get_attempt_questions(
    attempt_id: str,
    current_user: CurrentUser = Depends(require_role("student")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Reload a standardized attempt's student-safe fixed question set.

    Ownership is enforced via ``get_results``. Correct answers and
    explanations are never part of this payload.
    """
    service = AssessmentService(db)
    try:
        attempt = await service.get_results(current_user.id, attempt_id)
    except AssessmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    assessment = await service.assessments.get_by_id(attempt.assessment_id)
    questions = (
        await service.get_fixed_questions(attempt.assessment_id)
        if assessment and service._is_standardized(assessment)
        else []
    )
    return AttemptQuestionsResponse(
        attempt_id=attempt.id,
        format=assessment.format if assessment else AssessmentFormat.ADAPTIVE,
        total_questions=len(assessment.question_ids) if assessment else 0,
        questions=questions,
        answered_question_ids=service.answered_ids(attempt),
        instructions=assessment.instructions if assessment else "",
    )


@router.post("/attempts/{attempt_id}/answer", response_model=SubmitAnswerResponse)
async def submit_answer(
    attempt_id: str,
    payload: SubmitAnswerRequest,
    current_user: CurrentUser = Depends(require_role("student")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = AssessmentService(db)
    try:
        attempt, next_question, is_correct, marks_awarded, code_result = await service.submit_answer(
            current_user.id,
            attempt_id,
            payload.session_token,
            payload.question_id,
            payload.response,
            payload.time_taken_sec,
        )
    except AssessmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return SubmitAnswerResponse(
        is_correct=is_correct,
        marks_awarded=marks_awarded,
        next_question=to_student_view(next_question) if next_question else None,
        attempt_status=attempt.status,
        code_result=code_result,
        answered_question_ids=service.answered_ids(attempt),
    )


@router.post("/attempts/{attempt_id}/finish", response_model=FinishAttemptResponse)
async def finish_attempt(
    attempt_id: str,
    payload: FinishAttemptRequest,
    current_user: CurrentUser = Depends(require_role("student")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Finalize an in-progress attempt using the answers submitted so far."""
    service = AssessmentService(db)
    try:
        attempt = await service.finish_attempt(
            current_user.id,
            attempt_id,
            payload.session_token,
        )
    except AssessmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    assessment = await service.assessments.get_by_id(attempt.assessment_id)
    total_marks = sum(a.marks_awarded for a in attempt.answers)
    max_possible_marks = sum(DIFFICULTY_MARKS[a.difficulty_at_time] for a in attempt.answers)
    if assessment and service._is_standardized(assessment):
        max_possible_marks = assessment.total_marks or max_possible_marks
        total_marks = max(0.0, min(float(total_marks), float(max_possible_marks)))
    return FinishAttemptResponse(
        attempt_id=attempt.id,
        status=attempt.status,
        questions_answered=len(attempt.answers),
        total_marks=total_marks,
        max_possible_marks=max_possible_marks,
        submitted_at=attempt.submitted_at,
    )


@router.post("/attempts/{attempt_id}/run-code", response_model=RunCodeResponse)
async def run_code(
    attempt_id: str,
    payload: RunCodeRequest,
    current_user: CurrentUser = Depends(require_role("student")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Run a coding question against its visible sample test cases."""
    service = AssessmentService(db)
    try:
        code_result = await service.run_code_sample(
            current_user.id,
            attempt_id,
            payload.session_token,
            payload.question_id,
            payload.code,
        )
    except AssessmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return RunCodeResponse(code_result=code_result)


@router.post("/attempts/{attempt_id}/violation", response_model=ViolationReportResponse)
async def report_violation(
    attempt_id: str,
    payload: ViolationReportRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_role("student")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Reports a client-detected anti-cheat event. `type` is a free-form
    string by convention — the frontend sends values like "tab_switch",
    "fullscreen_exit", "devtools_opened", "idle_timeout",
    "copy_paste_attempt" — the backend doesn't hardcode this list, it just
    counts occurrences and auto-submits once the assessment's configured
    threshold is reached.
    """
    service = AssessmentService(db)
    client_ip = request.client.host if request.client else None
    try:
        attempt, violation_count, max_violations, auto_submitted = await service.report_violation(
            current_user.id,
            attempt_id,
            payload.session_token,
            payload.type,
            payload.metadata,
            ip_address=client_ip,
        )
    except AssessmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return ViolationReportResponse(
        violation_count=violation_count,
        max_violations=max_violations,
        attempt_status=attempt.status,
        auto_submitted=auto_submitted,
    )


@router.get("/attempts/{attempt_id}/results", response_model=AttemptResultResponse)
async def get_attempt_results(
    attempt_id: str,
    current_user: CurrentUser = Depends(require_role("student")),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    service = AssessmentService(db)
    try:
        attempt = await service.get_results(current_user.id, attempt_id)
    except AssessmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    assessment = await service.assessments.get_by_id(attempt.assessment_id)
    standardized = assessment is not None and service._is_standardized(assessment)
    total_marks = sum(a.marks_awarded for a in attempt.answers)
    # Max possible marks reconstructed from each question's difficulty at
    # the time it was asked for adaptive attempts; standardized attempts use
    # the configured total so unanswered questions still count.
    max_possible_marks = sum(DIFFICULTY_MARKS[a.difficulty_at_time] for a in attempt.answers)
    if standardized and assessment is not None:
        max_possible_marks = assessment.total_marks or max_possible_marks
        total_marks = max(0.0, min(float(total_marks), float(max_possible_marks)))

    # Answer keys are revealed only once the attempt is actually submitted.
    revealed = attempt.status == AttemptStatus.SUBMITTED
    section_by_question: dict[str, str] = {}
    if standardized and assessment is not None:
        for section in assessment.sections:
            for question_id in section.get("question_ids", []):
                section_by_question[question_id] = section.get("name", "")

    question_repo = QuestionRepository(db)
    answer_details: list[AttemptAnswerDetail] = []
    for answer in attempt.answers:
        question = await question_repo.get_by_id(answer.question_id)
        code_result = CodeRunSummary(**answer.code_result) if answer.code_result else None
        max_marks = (
            question.marks
            if standardized and question
            else DIFFICULTY_MARKS[answer.difficulty_at_time]
        )
        answer_details.append(
            AttemptAnswerDetail(
                question_id=answer.question_id,
                type=answer.question_type or (question.type if question else None),
                text=question.text if question else "(question no longer available)",
                response=answer.response,
                is_correct=answer.is_correct,
                marks_awarded=answer.marks_awarded,
                max_marks=max_marks,
                code_result=code_result,
                correct_answer=question.correct_answer if revealed and question else None,
                explanation=question.explanation if revealed and question else None,
                section=section_by_question.get(answer.question_id),
            )
        )

    return AttemptResultResponse(
        attempt_id=attempt.id,
        status=attempt.status,
        total_marks=total_marks,
        max_possible_marks=max_possible_marks,
        questions_answered=len(attempt.answers),
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        answers=answer_details,
    )
