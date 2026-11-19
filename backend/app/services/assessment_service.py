"""
Adaptive assessment engine.

Selection strategy: start at Medium difficulty when the selected categories
have one; otherwise fall back to the next available level (Easy first, then
Hard) so a bank that only contains, say, easy coding questions can still be
attempted. A correct answer moves the NEXT question one level harder; a wrong
answer moves it one level easier (clamped at the Easy/Hard ends) — a simple,
transparent adaptive strategy matching the project's stated requirement,
rather than a more elaborate IRT/CAT model that would need calibrated
item-difficulty parameters this system doesn't have yet.

Grading: MCQ is exact-match against `correct_answer`, fully automatic.
Coding questions are executed against one or more stdin/stdout test cases
(see `code_execution_service`) — a question is correct only when every test
case passes. Descriptive questions are stored ungraded (`is_correct=None`)
and scored by a TPO/admin reviewer through the manual-review endpoints; there
is no reliable free/automatic way to grade free-text answers without an
LLM-grading pipeline, which is its own scope decision to make deliberately,
not bolt on as an afterthought.
"""
import asyncio
import random
import secrets
from datetime import datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.assessment import (
    DIFFICULTY_MARKS,
    DIFFICULTY_ORDER,
    OBJECTIVE_QUESTION_TYPES,
    AssessmentAttemptInDB,
    AssessmentFormat,
    AssessmentInDB,
    AssessmentPublishStatus,
    AttemptStatus,
    CodeRunSummary,
    DifficultyLevel,
    QuestionInDB,
    QuestionStudentView,
    QuestionType,
    TestCase,
)
from app.models.drive import AssessmentStatus
from app.repositories.activity_log_repository import log_activity
from app.repositories.application_repository import ApplicationRepository
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.attempt_repository import AttemptRepository
from app.repositories.drive_repository import PlacementDriveRepository
from app.repositories.profile_repositories import StudentRepository, TPORepository
from app.repositories.question_repository import QuestionRepository
from app.services.code_execution_service import execute_code
from app.services.knowledge_tracing_service import KnowledgeTracingService


class AssessmentError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def to_student_view(question: QuestionInDB) -> QuestionStudentView:
    shuffled_options = random.sample(question.options, len(question.options)) if question.options else []
    visible_cases = (
        [case for case in question.test_cases if not case.is_hidden]
        if question.type == QuestionType.CODING
        else []
    )
    return QuestionStudentView(
        id=question.id,
        difficulty=question.difficulty,
        type=question.type,
        text=question.text,
        options=shuffled_options,
        marks=question.marks,
        language=question.language if question.type == QuestionType.CODING else None,
        starter_code=question.starter_code if question.type == QuestionType.CODING else None,
        visible_test_cases=visible_cases,
    )


def _effective_test_cases(question: QuestionInDB) -> list[TestCase]:
    """Test cases to run for a coding question.

    New questions carry an explicit list. Legacy coding questions (created
    when grading was exact-match) only have ``correct_answer``; treat that as
    a single empty-input case so they keep working instead of silently
    becoming ungradable.
    """
    if question.test_cases:
        return question.test_cases
    if question.correct_answer:
        return [TestCase(input="", expected_output=question.correct_answer, is_hidden=True, name="Expected output")]
    return []


def _grade(question: QuestionInDB, response: str) -> bool | None:
    if question.type == QuestionType.MCQ:
        return response.strip() == (question.correct_answer or "").strip()
    if question.type == QuestionType.TRUE_FALSE:
        return response.strip().lower() == (question.correct_answer or "").strip().lower()
    if question.type == QuestionType.MULTIPLE_SELECT:
        # ``correct_answer`` is stored as option texts joined by "|" in the
        # administrator's chosen order. The student sends their selection in
        # the same format; order is deliberately ignored (a set comparison).
        expected = {part.strip() for part in (question.correct_answer or "").split("|") if part.strip()}
        given = {part.strip() for part in response.split("|") if part.strip()}
        return bool(expected) and expected == given
    return None  # coding is graded by executing test cases; descriptive is manual review


def _adjust_difficulty(current: DifficultyLevel, was_correct: bool) -> DifficultyLevel:
    idx = DIFFICULTY_ORDER.index(current)
    if was_correct:
        idx = min(idx + 1, len(DIFFICULTY_ORDER) - 1)
    else:
        idx = max(idx - 1, 0)
    return DIFFICULTY_ORDER[idx]


class AssessmentService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.assessments = AssessmentRepository(db)
        self.attempts = AttemptRepository(db)
        self.questions = QuestionRepository(db)
        self.students = StudentRepository(db)
        self.applications = ApplicationRepository(db)
        self.drives = PlacementDriveRepository(db)
        self.kts = KnowledgeTracingService(db)

    async def _resolve_student_id(self, student_user_id: str) -> str:
        student = await self.students.get_by_user_id(student_user_id)
        if not student:
            raise AssessmentError("Student profile not found.", 404)
        return student.id

    @staticmethod
    def _is_standardized(assessment: AssessmentInDB) -> bool:
        """Only assessments with a stored fixed set use the standardized path."""
        return assessment.format == AssessmentFormat.STANDARDIZED and bool(assessment.question_ids)

    async def compute_adaptive_total_marks(
        self, category_ids: list[str], question_pool_size: int
    ) -> int:
        """Upper bound on the marks an adaptive attempt can earn.

        Adaptive selection asks at most ``question_pool_size`` questions from
        the assessment's categories, so the best possible score is the sum of
        the highest-mark questions available. Storing this at creation time
        means the admin/student views no longer report ``0`` marks until an
        attempt happens to be graded.
        """
        if question_pool_size <= 0:
            return 0
        query: dict = {"status": {"$in": ["active", None]}}
        if category_ids:
            query["category_id"] = {"$in": category_ids}
        questions = await self.questions.find_many(query, limit=5000)
        marks = sorted((int(q.marks) for q in questions), reverse=True)
        return int(sum(marks[:question_pool_size]))

    async def _ordered_questions(self, assessment: AssessmentInDB) -> list[QuestionInDB]:
        """Return the assessment's fixed questions in their stored order."""
        return await self.questions.find_by_ids(assessment.question_ids)

    async def get_fixed_questions(self, assessment_id: str) -> list[QuestionStudentView]:
        """Student-safe ordered questions for a standardized attempt."""
        assessment = await self.assessments.get_by_id(assessment_id)
        if not assessment or not self._is_standardized(assessment):
            return []
        return [to_student_view(q) for q in await self._ordered_questions(assessment)]

    @staticmethod
    def answered_ids(attempt: AssessmentAttemptInDB) -> list[str]:
        return [a.question_id for a in attempt.answers]

    async def start_attempt(
        self,
        student_user_id: str,
        assessment_id: str,
        fingerprint_hash: str | None = None,
        ip_address: str | None = None,
        application_id: str | None = None,
    ) -> tuple[AssessmentAttemptInDB, QuestionInDB | None]:
        student_id = await self._resolve_student_id(student_user_id)

        assessment = await self.assessments.get_by_id(assessment_id)
        if not assessment:
            raise AssessmentError("Assessment not found.", 404)

        is_standardized = self._is_standardized(assessment)
        if is_standardized:
            if assessment.status == AssessmentPublishStatus.DRAFT:
                raise AssessmentError("This assessment is not published yet.", 403)
            if not assessment.allow_retake:
                previous = await self.attempts.find_many(
                    {
                        "assessment_id": assessment.id,
                        "student_id": student_id,
                        "status": AttemptStatus.SUBMITTED.value,
                    },
                    limit=1,
                )
                if previous:
                    raise AssessmentError(
                        "You have already submitted this assessment and retakes are not allowed.", 403
                    )

        # A drive-linked assessment (drive_id set) enforces application
        # linkage and drive rules. Practice assessments are never linked to a
        # drive, so any application_id sent for them is ignored.
        is_drive_assessment = assessment.drive_id is not None
        application = None
        if is_drive_assessment:
            if not application_id:
                raise AssessmentError("Drive assessments require an application ID.", 400)
            application = await self.applications.get_by_id(application_id)
            if not application or application.student_id != student_id:
                raise AssessmentError("Application not found for this student.", 404)
            drive = await self.drives.get_by_id(application.drive_id)
            if not drive:
                raise AssessmentError("Drive not found.", 404)
            if drive.required_assessment_id and drive.required_assessment_id != assessment.id:
                raise AssessmentError("This assessment does not match the drive requirements.", 400)
            if drive.assessment_deadline and drive.assessment_deadline < datetime.utcnow():
                raise AssessmentError("The assessment deadline for this drive has passed.", 400)

        # Resume an in-progress attempt instead of creating a second one. This
        # matters when a student navigates away or refreshes: without it, the
        # old attempt stays in_progress forever while the new attempt silently
        # replaces the application's attempt link.
        existing_attempt = None
        if application and application.assessment_attempt_id:
            existing_attempt = await self.attempts.get_by_id(application.assessment_attempt_id)
        if not existing_attempt:
            in_progress = await self.attempts.find_many(
                {
                    "assessment_id": assessment.id,
                    "student_id": student_id,
                    "status": AttemptStatus.IN_PROGRESS.value,
                },
                limit=1,
                sort=[("started_at", -1)],
            )
            existing_attempt = in_progress[0] if in_progress else None

        if existing_attempt and existing_attempt.status == AttemptStatus.IN_PROGRESS:
            deadline = existing_attempt.started_at + timedelta(seconds=assessment.time_limit_sec)
            if datetime.utcnow() <= deadline:
                current_question = (
                    await self.questions.get_by_id(existing_attempt.current_question_id)
                    if existing_attempt.current_question_id
                    else None
                )
                if is_standardized:
                    # Fixed-set attempts navigate freely, so "current" simply
                    # means the first unanswered question in the stored order.
                    answered = set(self.answered_ids(existing_attempt))
                    ordered = await self._ordered_questions(assessment)
                    remaining = [q for q in ordered if q.id not in answered]
                    current_question = remaining[0] if remaining else (ordered[0] if ordered else None)
                    if current_question and existing_attempt.current_question_id != current_question.id:
                        await self.attempts.update_by_id(
                            existing_attempt.id, {"current_question_id": current_question.id}
                        )
                if current_question:
                    if application and application.assessment_attempt_id != existing_attempt.id:
                        await self.applications.update_by_id(
                            application.id,
                            {
                                "assessment_attempt_id": existing_attempt.id,
                                "assessment_status": AssessmentStatus.PENDING.value,
                            },
                        )
                    await log_activity(
                        self.db,
                        student_user_id,
                        action="attempt_resumed",
                        entity="assessment_attempt",
                        entity_id=existing_attempt.id,
                        metadata={
                            "assessment_id": assessment_id,
                            "application_id": application_id,
                            "assessment_type": assessment.type.value,
                        },
                        ip_address=ip_address,
                    )
                    return existing_attempt, current_question
            # Expired, or the attempt has no current question: close it out
            # before starting a fresh one so it cannot linger forever.
            await self._finalize_attempt(existing_attempt)

        if is_standardized:
            # Every student receives the identical ordered set that was fixed
            # at generation time — no per-student randomness or regeneration.
            ordered = await self._ordered_questions(assessment)
            if len(ordered) != len(assessment.question_ids) or not ordered:
                raise AssessmentError(
                    "This assessment's fixed question set is incomplete. Contact your administrator.",
                    422,
                )
            first_question = ordered[0]
            first_difficulty = first_question.difficulty
            asked_ids = list(assessment.question_ids)
        else:
            first_difficulty = DifficultyLevel.MEDIUM
            first_question = await self.questions.get_random_unused(
                category_ids=assessment.category_ids,
                difficulty=first_difficulty.value,
                exclude_ids=[],
            )
            if not first_question:
                # Question banks don't have to contain a medium-difficulty item
                # in every category (the common case is a category with only
                # easy questions, e.g. a single coding problem). Fall back to
                # the other levels instead of refusing to start the assessment.
                for fallback_difficulty in DIFFICULTY_ORDER:
                    if fallback_difficulty == first_difficulty:
                        continue
                    first_question = await self.questions.get_random_unused(
                        category_ids=assessment.category_ids,
                        difficulty=fallback_difficulty.value,
                        exclude_ids=[],
                    )
                    if first_question:
                        first_difficulty = fallback_difficulty
                        break
            if not first_question:
                raise AssessmentError(
                    "No questions available for this assessment yet. "
                    "Add at least one question to the categories selected for this assessment.",
                    422,
                )
            asked_ids = [first_question.id]

        attempt = await self.attempts.create(
            {
                "assessment_id": assessment.id,
                "student_id": student_id,
                "session_token": secrets.token_urlsafe(24),
                "asked_question_ids": asked_ids,
                "current_question_id": first_question.id,
                "current_difficulty": first_difficulty.value,
                "answers": [],
                "violations": [],
                "status": AttemptStatus.IN_PROGRESS.value,
                "started_at": datetime.utcnow(),
                "submitted_at": None,
                "ip_address": ip_address,
                "fingerprint_hash": fingerprint_hash,
            }
        )

        # Link attempt to application only for drive assessments
        if application:
            await self.applications.update_by_id(
                application.id,
                {
                    "assessment_attempt_id": attempt.id,
                    "assessment_status": AssessmentStatus.PENDING.value,
                },
            )

        await log_activity(
            self.db,
            student_user_id,
            action="attempt_started",
            entity="assessment_attempt",
            entity_id=attempt.id,
            metadata={
                "assessment_id": assessment_id,
                "application_id": application_id,
                "assessment_type": assessment.type.value,
            },
            ip_address=ip_address,
        )
        return attempt, first_question

    async def _require_in_progress_attempt(
        self, resolved_student_id: str, attempt_id: str, session_token: str
    ) -> tuple[AssessmentAttemptInDB, AssessmentInDB]:
        attempt = await self.attempts.get_by_id(attempt_id)
        if not attempt:
            raise AssessmentError("Attempt not found.", 404)
        if attempt.student_id != resolved_student_id:
            raise AssessmentError("This is not your attempt.", 403)
        if attempt.session_token != session_token:
            raise AssessmentError("Invalid session token for this attempt.", 403)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise AssessmentError("This attempt has already been submitted.", 400)

        assessment = await self.assessments.get_by_id(attempt.assessment_id)
        if datetime.utcnow() > attempt.started_at + timedelta(seconds=assessment.time_limit_sec):
            await self._finalize_attempt(attempt)
            raise AssessmentError("Time limit exceeded. This attempt has been auto-submitted.", 400)

        return attempt, assessment

    async def _finalize_attempt(self, attempt: AssessmentAttemptInDB) -> AssessmentAttemptInDB:
        """Mark attempt submitted and update any linked application score and status."""
        now = datetime.utcnow()
        updated_attempt = await self.attempts.update_by_id(
            attempt.id,
            {
                "status": AttemptStatus.SUBMITTED.value,
                "submitted_at": now,
                "current_question_id": None,
            },
        )
        if not updated_attempt:
            return attempt

        assessment = await self.assessments.get_by_id(updated_attempt.assessment_id)
        total_marks, max_marks, score_pct = self._score_attempt(updated_attempt, assessment)
        await self._apply_score_to_applications(updated_attempt, assessment, total_marks, score_pct)

        # For practice assessments, we still update knowledge tracing but don't
        # link to applications (already handled by not setting assessment_attempt_id
        # for practice assessments in start_attempt)

        return updated_attempt

    def _score_attempt(
        self, attempt: AssessmentAttemptInDB, assessment: AssessmentInDB | None
    ) -> tuple[float, int, float]:
        """Return ``(total_marks, max_marks, score_pct)`` for an attempt.

        Standardized assessments use their configured total marks (and clamp
        negative-marking results at zero), while adaptive attempts keep the
        difficulty-derived maximum for the questions actually asked.
        """
        standardized = assessment is not None and self._is_standardized(assessment)
        total_marks = sum(a.marks_awarded for a in attempt.answers)
        max_marks = sum(DIFFICULTY_MARKS[a.difficulty_at_time] for a in attempt.answers)
        if standardized and assessment is not None:
            max_marks = assessment.total_marks or max_marks
            total_marks = max(0.0, min(float(total_marks), float(max_marks)))
        score_pct = round(100.0 * total_marks / max_marks, 1) if max_marks > 0 else 0.0
        return total_marks, max_marks, score_pct

    async def _apply_score_to_applications(
        self,
        attempt: AssessmentAttemptInDB,
        assessment: AssessmentInDB | None,
        total_marks: float,
        score_pct: float,
    ) -> None:
        """Persist the (possibly re-computed) score on every linked application.

        One attempt can in principle be linked to several applications, so this
        must not be capped at the repository default — a missed row here means
        an application silently never gets its pass/fail status updated.
        """
        standardized = assessment is not None and self._is_standardized(assessment)
        linked_apps = await self.applications.find_many(
            {"assessment_attempt_id": attempt.id}, limit=100
        )
        for app in linked_apps:
            drive = await self.drives.get_by_id(app.drive_id)
            pass_status = AssessmentStatus.PASSED.value
            if drive and drive.assessment_min_score_pct is not None:
                if score_pct < drive.assessment_min_score_pct:
                    pass_status = AssessmentStatus.FAILED.value
            elif standardized and assessment is not None and assessment.passing_marks:
                if total_marks < assessment.passing_marks:
                    pass_status = AssessmentStatus.FAILED.value

            await self.applications.update_by_id(
                app.id,
                {
                    "assessment_score_pct": score_pct,
                    "assessment_status": pass_status,
                },
            )

    async def submit_answer(
        self,
        student_user_id: str,
        attempt_id: str,
        session_token: str,
        question_id: str,
        response: str,
        time_taken_sec: float | None,
    ) -> tuple[AssessmentAttemptInDB, QuestionInDB | None, bool | None, float, CodeRunSummary | None]:
        student_id = await self._resolve_student_id(student_user_id)
        attempt, assessment = await self._require_in_progress_attempt(student_id, attempt_id, session_token)

        standardized = self._is_standardized(assessment)
        if standardized:
            if question_id not in assessment.question_ids:
                raise AssessmentError("This question is not part of this assessment.", 400)
            is_change = any(a.question_id == question_id for a in attempt.answers)
        else:
            if attempt.current_question_id != question_id:
                raise AssessmentError("This is not the current question for this attempt.", 400)
            is_change = False

        question = await self.questions.get_by_id(question_id)
        if not question:
            raise AssessmentError("Question not found.", 404)

        code_result: CodeRunSummary | None = None
        if question.type == QuestionType.CODING:
            test_cases = _effective_test_cases(question)
            if not test_cases:
                raise AssessmentError("This coding question has no test cases configured.", 500)
            # Running student code is blocking, so keep it off the event loop.
            code_result = await asyncio.to_thread(execute_code, question.language, response, test_cases)
            if code_result.status in {"disabled", "unsupported_language", "error"}:
                # These are server configuration problems, not wrong answers.
                raise AssessmentError(
                    code_result.error or "Code execution is unavailable right now.", 503
                )
            is_correct = code_result.all_passed
        else:
            is_correct = _grade(question, response)

        marks_awarded: float = question.marks if is_correct else 0
        if is_correct is False and standardized:
            # Negative marking applies only to wrong, auto-gradable answers on
            # standardized assessments. Ungraded (descriptive) answers are None.
            marks_awarded = -abs(assessment.negative_marks)

        if time_taken_sec is not None and time_taken_sec < 3.0:
            await log_activity(
                self.db,
                student_user_id,
                action="fast_answer_detected",
                entity="assessment_attempt",
                entity_id=attempt.id,
                metadata={"question_id": question_id, "time_taken_sec": time_taken_sec},
            )

        if is_correct is not None and not is_change:
            # A revised answer replaces the earlier record; don't double-count
            # it in knowledge tracing.
            for skill_tag in question.skill_tags:
                await self.kts.update_mastery(student_id, skill_tag, is_correct, question.difficulty)

        answer_record = {
            "question_id": question_id,
            "response": response,
            "is_correct": is_correct,
            "marks_awarded": marks_awarded,
            "time_taken_sec": time_taken_sec,
            "difficulty_at_time": question.difficulty.value,
            "question_type": question.type.value,
            "code_result": code_result.model_dump() if code_result else None,
        }
        new_answers = [a.model_dump(mode="json") for a in attempt.answers]
        if standardized:
            # Answers may be changed before submission: keep one record per
            # question rather than appending duplicates.
            new_answers = [a for a in new_answers if a["question_id"] != question_id]
        new_answers.append(answer_record)

        if standardized:
            # The fixed set can be answered in any order and is finalized only
            # by finish / timeout / violation threshold — never per question.
            update_data: dict = {"answers": new_answers}
            answered = {a["question_id"] for a in new_answers}
            remaining = [qid for qid in assessment.question_ids if qid not in answered]
            if remaining:
                update_data["current_question_id"] = remaining[0]
            updated_attempt = await self.attempts.update_by_id(attempt.id, update_data)
            return updated_attempt, None, is_correct, marks_awarded, code_result

        pool_exhausted = len(new_answers) >= assessment.question_pool_size
        next_question = None
        next_difficulty = attempt.current_difficulty

        if not pool_exhausted:
            next_difficulty = _adjust_difficulty(attempt.current_difficulty, bool(is_correct))
            next_question = await self.questions.get_random_unused(
                category_ids=assessment.category_ids,
                difficulty=next_difficulty.value,
                exclude_ids=attempt.asked_question_ids,
            )
            if not next_question:
                for fallback_difficulty in DIFFICULTY_ORDER:
                    if fallback_difficulty == next_difficulty:
                        continue
                    next_question = await self.questions.get_random_unused(
                        category_ids=assessment.category_ids,
                        difficulty=fallback_difficulty.value,
                        exclude_ids=attempt.asked_question_ids,
                    )
                    if next_question:
                        next_difficulty = fallback_difficulty
                        break

        update_data: dict = {"answers": new_answers}
        if next_question:
            update_data["asked_question_ids"] = attempt.asked_question_ids + [next_question.id]
            update_data["current_question_id"] = next_question.id
            update_data["current_difficulty"] = next_difficulty.value
            updated_attempt = await self.attempts.update_by_id(attempt.id, update_data)
        else:
            # Assessment is finished
            await self.attempts.update_by_id(attempt.id, update_data)
            refreshed = await self.attempts.get_by_id(attempt.id)
            updated_attempt = await self._finalize_attempt(refreshed)

        return updated_attempt, next_question, is_correct, marks_awarded, code_result

    async def finish_attempt(
        self,
        student_user_id: str,
        attempt_id: str,
        session_token: str,
    ) -> AssessmentAttemptInDB:
        """Finish an in-progress attempt early.

        The score is computed from the answers already submitted. This keeps
        an early exit (or an expired client timer) from leaving an orphaned
        ``in_progress`` attempt that never appears in results or rankings.
        """
        student_id = await self._resolve_student_id(student_user_id)
        attempt, _ = await self._require_in_progress_attempt(
            student_id, attempt_id, session_token
        )
        return await self._finalize_attempt(attempt)

    async def run_code_sample(
        self,
        student_user_id: str,
        attempt_id: str,
        session_token: str,
        question_id: str,
        code: str,
    ) -> CodeRunSummary:
        """Run a student's code against only the *visible* sample test cases.

        This is a convenience for iteration before submitting. Hidden test
        cases are never run here, so the endpoint cannot be used to probe the
        hidden expectations.
        """
        student_id = await self._resolve_student_id(student_user_id)
        attempt, assessment = await self._require_in_progress_attempt(student_id, attempt_id, session_token)

        if self._is_standardized(assessment):
            if question_id not in assessment.question_ids:
                raise AssessmentError("This question is not part of this assessment.", 400)
        elif attempt.current_question_id != question_id:
            raise AssessmentError("This is not the current question for this attempt.", 400)

        question = await self.questions.get_by_id(question_id)
        if not question:
            raise AssessmentError("Question not found.", 404)
        if question.type != QuestionType.CODING:
            raise AssessmentError("Only coding questions can be run.", 400)

        visible_cases = [case for case in _effective_test_cases(question) if not case.is_hidden]
        return await asyncio.to_thread(
            execute_code, question.language, code, visible_cases, only_visible=True
        )

    async def get_results(self, student_user_id: str, attempt_id: str) -> AssessmentAttemptInDB:
        student_id = await self._resolve_student_id(student_user_id)
        attempt = await self.attempts.get_by_id(attempt_id)
        if not attempt:
            raise AssessmentError("Attempt not found.", 404)
        if attempt.student_id != student_id:
            raise AssessmentError("This is not your attempt.", 403)
        return attempt

    async def report_violation(
        self,
        student_user_id: str,
        attempt_id: str,
        session_token: str,
        violation_type: str,
        metadata: dict,
        ip_address: str | None = None,
    ) -> tuple[AssessmentAttemptInDB, int, int, bool]:
        student_id = await self._resolve_student_id(student_user_id)
        attempt, assessment = await self._require_in_progress_attempt(student_id, attempt_id, session_token)

        violation_record = {
            "type": violation_type,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata,
        }
        new_violations = attempt.violations + [violation_record]

        max_violations = assessment.anti_cheat_config.get("max_violations", 3)
        violation_count = len(new_violations)
        auto_submitted = violation_count >= max_violations

        update_data: dict = {"violations": new_violations}
        if auto_submitted:
            await self.attempts.update_by_id(attempt.id, update_data)
            refreshed = await self.attempts.get_by_id(attempt.id)
            updated_attempt = await self._finalize_attempt(refreshed)
        else:
            updated_attempt = await self.attempts.update_by_id(attempt.id, update_data)

        await log_activity(
            self.db,
            student_user_id,
            action="violation_reported",
            entity="assessment_attempt",
            entity_id=attempt.id,
            metadata={"type": violation_type, "count": violation_count, "auto_submitted": auto_submitted},
            ip_address=ip_address,
        )

        return updated_attempt, violation_count, max_violations, auto_submitted

    # ------------------------------------------------------------------
    # Manual review of descriptive answers
    # ------------------------------------------------------------------
    async def _assert_can_review(
        self,
        assessment: AssessmentInDB,
        reviewer_role: str,
        reviewer_user_id: str,
    ) -> None:
        """Admin may review anything; a TPO only their own drive's attempts.

        Practice assessments have no owning drive, so any TPO may review them —
        they are placement-team work rather than a specific drive's data.
        """
        if reviewer_role == "admin":
            return
        if reviewer_role != "tpo":
            raise AssessmentError("You do not have permission to review attempts.", 403)
        if assessment.drive_id:
            drive = await self.drives.get_by_id(assessment.drive_id)
            tpo = await TPORepository(self.db).get_by_user_id(reviewer_user_id)
            if not drive or not tpo or str(drive.created_by) != str(tpo.id):
                raise AssessmentError(
                    "You do not have permission to review attempts for this drive.", 403
                )

    async def _review_context(
        self, attempt_id: str, reviewer_role: str, reviewer_user_id: str
    ) -> tuple[AssessmentAttemptInDB, AssessmentInDB, object | None]:
        attempt = await self.attempts.get_by_id(attempt_id)
        if not attempt:
            raise AssessmentError("Attempt not found.", 404)
        assessment = await self.assessments.get_by_id(attempt.assessment_id)
        if not assessment:
            raise AssessmentError("Assessment not found.", 404)
        await self._assert_can_review(assessment, reviewer_role, reviewer_user_id)
        if attempt.status != AttemptStatus.SUBMITTED:
            raise AssessmentError("Only submitted attempts can be reviewed.", 400)
        student = await self.students.get_by_id(attempt.student_id)
        return attempt, assessment, student

    async def pending_reviews(
        self, reviewer_role: str, reviewer_user_id: str
    ) -> list:
        """Submitted attempts with at least one ungraded descriptive answer."""
        from app.models.assessment import PendingReviewItem

        attempts = await self.attempts.find_many(
            {
                "status": AttemptStatus.SUBMITTED.value,
                "answers.question_type": QuestionType.DESCRIPTIVE.value,
            },
            limit=500,
            sort=[("submitted_at", -1)],
        )
        items = []
        for attempt in attempts:
            assessment = await self.assessments.get_by_id(attempt.assessment_id)
            if not assessment:
                continue
            try:
                await self._assert_can_review(assessment, reviewer_role, reviewer_user_id)
            except AssessmentError:
                continue
            pending = [
                a
                for a in attempt.answers
                if a.question_type == QuestionType.DESCRIPTIVE and a.graded_at is None
            ]
            if not pending:
                continue
            student = await self.students.get_by_id(attempt.student_id)
            items.append(
                PendingReviewItem(
                    attempt_id=attempt.id,
                    assessment_id=assessment.id,
                    assessment_title=assessment.title,
                    assessment_type=assessment.type,
                    drive_id=assessment.drive_id,
                    student_id=attempt.student_id,
                    student_name=student.name if student else None,
                    submitted_at=attempt.submitted_at,
                    pending_count=len(pending),
                    total_answers=len(attempt.answers),
                )
            )
        return items

    async def get_review(
        self, attempt_id: str, reviewer_role: str, reviewer_user_id: str
    ):
        from app.models.assessment import AttemptReviewAnswer, AttemptReviewResponse

        attempt, assessment, student = await self._review_context(
            attempt_id, reviewer_role, reviewer_user_id
        )
        total_marks, max_possible_marks, _ = self._score_attempt(attempt, assessment)
        answers = []
        pending_count = 0
        for answer in attempt.answers:
            if answer.question_type != QuestionType.DESCRIPTIVE:
                continue
            question = await self.questions.get_by_id(answer.question_id)
            if answer.graded_at is None:
                pending_count += 1
            answers.append(
                AttemptReviewAnswer(
                    question_id=answer.question_id,
                    question_text=question.text if question else "(question no longer available)",
                    response=answer.response,
                    max_marks=question.marks
                    if question
                    else DIFFICULTY_MARKS[answer.difficulty_at_time],
                    marks_awarded=answer.marks_awarded,
                    is_correct=answer.is_correct,
                    graded_at=answer.graded_at,
                    feedback=answer.feedback,
                    skill_tags=list(question.skill_tags) if question else [],
                )
            )
        return AttemptReviewResponse(
            attempt_id=attempt.id,
            assessment_id=assessment.id,
            assessment_title=assessment.title,
            assessment_type=assessment.type,
            drive_id=assessment.drive_id,
            student_id=attempt.student_id,
            student_name=student.name if student else None,
            status=attempt.status,
            submitted_at=attempt.submitted_at,
            pending_count=pending_count,
            total_marks=total_marks,
            max_possible_marks=max_possible_marks,
            answers=answers,
        )

    async def grade_descriptive(
        self,
        attempt_id: str,
        reviewer_role: str,
        reviewer_user_id: str,
        question_id: str,
        marks_awarded: float,
        feedback: str | None = None,
    ):
        """Score one descriptive answer and refresh the attempt/application score."""
        from app.models.assessment import ManualGradeResponse

        attempt, assessment, _ = await self._review_context(
            attempt_id, reviewer_role, reviewer_user_id
        )
        target = next((a for a in attempt.answers if a.question_id == question_id), None)
        if not target:
            raise AssessmentError("This question was not answered in this attempt.", 404)
        if target.question_type != QuestionType.DESCRIPTIVE:
            raise AssessmentError("Only descriptive answers can be manually graded.", 400)

        question = await self.questions.get_by_id(question_id)
        max_marks = question.marks if question else DIFFICULTY_MARKS[target.difficulty_at_time]
        marks = max(0.0, min(float(marks_awarded), float(max_marks)))
        graded_at = datetime.utcnow()
        is_correct = marks >= max_marks

        new_answers = []
        for answer in attempt.answers:
            data = answer.model_dump(mode="json")
            if answer.question_id == question_id:
                data.update(
                    {
                        "marks_awarded": marks,
                        "is_correct": is_correct,
                        "graded_at": graded_at,
                        "graded_by": reviewer_user_id,
                        "feedback": (feedback or "").strip() or None,
                    }
                )
            new_answers.append(data)

        updated = await self.attempts.update_by_id(attempt.id, {"answers": new_answers})
        if not updated:
            raise AssessmentError("Attempt not found.", 404)

        total_marks, max_possible_marks, score_pct = self._score_attempt(updated, assessment)
        await self._apply_score_to_applications(updated, assessment, total_marks, score_pct)
        pending_count = sum(
            1
            for a in updated.answers
            if a.question_type == QuestionType.DESCRIPTIVE and a.graded_at is None
        )

        await log_activity(
            self.db,
            reviewer_user_id,
            action="descriptive_answer_graded",
            entity="assessment_attempt",
            entity_id=attempt.id,
            metadata={
                "question_id": question_id,
                "marks_awarded": marks,
                "max_marks": max_marks,
                "pending_count": pending_count,
            },
        )

        return ManualGradeResponse(
            attempt_id=attempt.id,
            question_id=question_id,
            marks_awarded=marks,
            is_correct=is_correct,
            pending_count=pending_count,
            total_marks=total_marks,
            max_possible_marks=max_possible_marks,
        )
