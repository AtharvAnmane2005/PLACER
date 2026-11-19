"""Seed the student cohort and all activity that hangs off it.

Fifty students get a user, a profile, a real (small) PDF resume and a
deterministic set of applications. A realistic subset then *takes* the
practice and drive assessments through ``AssessmentService`` — the same
service the API uses — so scores, application pass/fail status and knowledge
states are produced by the real grading pipeline (including hidden coding
tests) rather than being written by hand.

The step is idempotent: users/profiles/resumes/applications are reused, and a
student who already has a submitted attempt for an assessment is not asked to
take it again.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from app.core.security import hash_password
from app.core.skill_taxonomy import canonicalize_skills
from app.models.assessment import (
    DIFFICULTY_MARKS,
    AssessmentFormat,
    AssessmentPublishStatus,
    AttemptStatus,
    CodingLanguage,
    QuestionType,
)
from app.models.drive import ApplicationStatus, AssessmentStatus, DriveStatus, RejectionReason
from app.models.resume import ParsedResumeData
from app.models.user import UserRole
from app.repositories.application_repository import ApplicationRepository
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.drive_repository import PlacementDriveRepository
from app.repositories.profile_repositories import StudentRepository
from app.repositories.resume_repository import ResumeRepository
from app.repositories.user_repository import UserRepository
from app.services.assessment_service import AssessmentError, AssessmentService
from app.services.drive_service import DriveError, DriveService
from app.services.storage_service import StorageService

from scripts.seed import data_coding
from scripts.seed.context import (
    SEED_PASSWORD,
    SYNTHETIC,
    build_pdf,
    now,
    stable_oid,
    student_email,
)

# ---------------------------------------------------------------------------
# Cohort composition
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "Aarav", "Aditi", "Advait", "Aisha", "Akash", "Ananya", "Aniket", "Anjali",
    "Arjun", "Arpita", "Aryan", "Avni", "Bhavya", "Chirag", "Dhruv", "Divya",
    "Esha", "Farhan", "Gautam", "Gauri", "Harini", "Harsh", "Ishita", "Jatin",
    "Kabir", "Kavya", "Kirti", "Kunal", "Lakshmi", "Manav", "Meera", "Mohit",
    "Nandini", "Neel", "Nikhil", "Nisha", "Omkar", "Pooja", "Pranav", "Priya",
    "Rahul", "Riya", "Rohan", "Sakshi", "Sameer", "Sanjana", "Shreya",
    "Siddharth", "Tanvi", "Varun",
]
LAST_NAMES = [
    "Sharma", "Verma", "Iyer", "Nair", "Patel", "Reddy", "Gupta", "Menon",
    "Singh", "Das", "Joshi", "Rao", "Mehta", "Kulkarni", "Bose", "Chawla",
    "Desai", "Ghosh", "Jain", "Kapoor", "Khanna", "Kumar", "Malhotra",
    "Mishra", "Mukherjee", "Naidu", "Pandey", "Pillai", "Rajan", "Sahu",
    "Saxena", "Sen", "Shah", "Shetty", "Sinha", "Srinivasan", "Thakur",
    "Tripathi", "Varma", "Venkatesh", "Yadav", "Bhatt", "Chopra", "Dutta",
    "Hegde", "Kaur", "Mahajan", "Narayan", "Prasad", "Sethi",
]

DEPARTMENTS = (
    ["Computer Science"] * 18
    + ["Information Technology"] * 10
    + ["Electronics and Communication"] * 8
    + ["Electrical Engineering"] * 6
    + ["Mathematics and Computing"] * 5
    + ["Statistics"] * 3
)

DEPARTMENT_SKILLS: dict[str, list[str]] = {
    "Computer Science": [
        "Python", "Java", "JavaScript", "React", "SQL", "MongoDB", "Git",
        "Data Structures", "Algorithms", "Docker", "REST API", "Machine Learning",
    ],
    "Information Technology": [
        "SQL", "Python", "JavaScript", "React", "REST API", "Git", "AWS",
        "Docker", "Linux", "MongoDB", "Node.js", "Cloud",
    ],
    "Electronics and Communication": [
        "C", "C++", "Python", "Embedded Systems", "Microcontrollers",
        "Computer Networks", "Linux", "Git", "Signal Processing", "Operating Systems",
    ],
    "Electrical Engineering": [
        "C", "C++", "MATLAB", "Python", "Embedded Systems", "Microcontrollers",
        "Git", "Control Systems", "Power Systems",
    ],
    "Mathematics and Computing": [
        "Python", "SQL", "Statistics", "Machine Learning", "Pandas", "NumPy",
        "Git", "Data Structures", "Algorithms", "Probability",
    ],
    "Statistics": [
        "SQL", "Python", "Statistics", "Pandas", "R", "Data Visualisation",
        "Excel", "Machine Learning", "NumPy",
    ],
}

EXTRA_SKILLS = [
    "Docker", "AWS", "Kubernetes", "Machine Learning", "Cybersecurity",
    "Cloud", "MongoDB", "React", "REST API", "Data Structures",
]

PROJECTS: dict[str, list[dict]] = {
    "Computer Science": [
        {"title": "Campus Event Portal", "description": "Full-stack event registration app with React and FastAPI."},
        {"title": "Placement Analytics Dashboard", "description": "MongoDB aggregation pipeline feeding a React dashboard."},
    ],
    "Information Technology": [
        {"title": "Cloud File Sync", "description": "Dockerised file sync service with role-based access."},
        {"title": "Network Monitor", "description": "Python agent that samples latency and alerts on thresholds."},
    ],
    "Electronics and Communication": [
        {"title": "Sensor Gateway", "description": "ESP32 gateway publishing sensor telemetry over MQTT."},
        {"title": "Digital Filter Design", "description": "MATLAB/Simulink filter for audio signal cleanup."},
    ],
    "Electrical Engineering": [
        {"title": "Load Forecasting", "description": "Regression model for short-term feeder load."},
        {"title": "Motor Controller", "description": "Embedded C controller for a BLDC motor test rig."},
    ],
    "Mathematics and Computing": [
        {"title": "Forecasting Toolkit", "description": "Time-series cross-validation utilities in Python."},
        {"title": "Graph Algorithms Notebook", "description": "Reference implementations with complexity notes."},
    ],
    "Statistics": [
        {"title": "Survey Analysis", "description": "R and Python analysis of a campus wellbeing survey."},
        {"title": "Experiment Design", "description": "A/B test power analysis and reporting template."},
    ],
}

CODING_BY_TITLE = {problem["title"].strip().lower(): problem for problem in data_coding.PROBLEMS}


def _student_spec(index: int) -> dict:
    """Deterministic profile for student ``index`` (1-based)."""
    name = f"{FIRST_NAMES[index - 1]} {LAST_NAMES[index - 1]}"
    department = DEPARTMENTS[((index - 1) * 7) % len(DEPARTMENTS)]
    batch_year = 2026 if index % 10 <= 7 else 2027
    cgpa = round(6.6 + (((index - 1) * 37) % 29) / 10, 1)
    skills = canonicalize_skills(
        DEPARTMENT_SKILLS[department] + [EXTRA_SKILLS[(index * 3) % len(EXTRA_SKILLS)]]
    )
    email = student_email(index)
    return {
        "index": index,
        "email": email,
        "name": name,
        "department": department,
        "batch_year": batch_year,
        "cgpa": cgpa,
        "phone": f"+91 90000 {10000 + index:05d}",
        "linkedin_url": f"https://linkedin.com/in/placer-student{index:02d}",
        "github_url": f"https://github.com/placer-student{index:02d}",
        "skills": skills,
        "achievements": [
            f"Finalist in the {department} project showcase (2025).",
            "Completed a 6-week industry readiness workshop.",
        ],
        "certificates": [
            "Python for Data Science (online)",
            "Cloud Fundamentals (online)",
        ],
        "projects": PROJECTS[department],
    }


def _resume_lines(spec: dict) -> list[str]:
    return [
        spec["name"],
        spec["email"],
        spec["phone"],
        f"{spec['department']} | Batch {spec['batch_year']} | CGPA {spec['cgpa']}",
        "",
        "SKILLS",
        ", ".join(spec["skills"]),
        "",
        "EDUCATION",
        f"B.Tech {spec['department']}, Placer Institute of Technology, {spec['batch_year']}",
        "",
        "PROJECTS",
        *[
            f"{project['title']} - {project['description']}"
            for project in spec["projects"]
        ],
        "",
        "CERTIFICATIONS",
        *spec["certificates"],
    ]


async def _ensure_students(
    db: AsyncIOMotorDatabase, log=print
) -> list[tuple[object, object, dict]]:
    users = UserRepository(db)
    students = StudentRepository(db)
    resumes = ResumeRepository(db)
    storage = StorageService()
    cohort: list[tuple[object, object, dict]] = []

    for index in range(1, 51):
        spec = _student_spec(index)
        user = await users.get_by_email(spec["email"])
        if not user:
            user = await users.create(
                {
                    "_id": stable_oid(f"student-user:{index}"),
                    "email": spec["email"],
                    "password_hash": hash_password(SEED_PASSWORD),
                    "role": UserRole.STUDENT.value,
                    "auth_provider": "local",
                    "is_active": True,
                    "created_at": now() - timedelta(days=120 - index),
                    "last_login": None,
                    **SYNTHETIC,
                }
            )

        student = await students.get_by_user_id(user.id)
        if not student:
            student = await students.create(
                {
                    "_id": stable_oid(f"student-profile:{index}"),
                    "user_id": user.id,
                    "name": spec["name"],
                    "department": spec["department"],
                    "batch_year": spec["batch_year"],
                    "cgpa": spec["cgpa"],
                    "phone": spec["phone"],
                    "linkedin_url": spec["linkedin_url"],
                    "github_url": spec["github_url"],
                    "portfolio_url": None,
                    "skills": spec["skills"],
                    "achievements": spec["achievements"],
                    "certificates": spec["certificates"],
                    "active_resume_id": None,
                    "profile_completeness_pct": 85.0 + (index % 16),
                    **SYNTHETIC,
                }
            )

        resume = await resumes.get_active_for_student(student.id)
        if not resume:
            lines = _resume_lines(spec)
            pdf = build_pdf(lines)
            file_url = await storage.save_pdf(
                pdf, student.id, f"v1-{stable_oid(f'resume-file:{index}')}"
            )
            parsed = ParsedResumeData(
                name=spec["name"],
                email=spec["email"],
                phone=spec["phone"],
                linkedin_url=spec["linkedin_url"],
                github_url=spec["github_url"],
                department=spec["department"],
                batch_year=spec["batch_year"],
                cgpa=spec["cgpa"],
                education=[
                    {
                        "degree": "B.Tech",
                        "department": spec["department"],
                        "institution": "Placer Institute of Technology",
                        "batch_year": spec["batch_year"],
                        "cgpa": spec["cgpa"],
                    }
                ],
                projects=spec["projects"],
                skills=spec["skills"],
                certifications=spec["certificates"],
                achievements=spec["achievements"],
                languages=["English", "Hindi"],
                parsing_metadata={"source": "synthetic_seed", "confidence": 0.9},
            )
            resume = await resumes.create(
                {
                    "_id": stable_oid(f"resume:{index}"),
                    "student_id": student.id,
                    "version": 1,
                    "original_filename": f"{spec['name'].replace(' ', '_')}_Resume.pdf",
                    "file_url": file_url,
                    "file_hash": hashlib.sha256(pdf).hexdigest(),
                    "file_size_bytes": len(pdf),
                    "parsed": parsed.model_dump(mode="json"),
                    "resume_text": "\n".join(lines),
                    "skill_set": spec["skills"],
                    "experience_years": 0.0 if index % 4 else 0.5,
                    "uploaded_at": now() - timedelta(days=90 - (index % 60)),
                    "is_active": True,
                    **SYNTHETIC,
                }
            )

        if str(student.active_resume_id or "") != resume.id:
            student = await students.update_by_id(
                student.id, {"active_resume_id": resume.id}
            )

        cohort.append((user, student, spec))
        if index % 10 == 0:
            log(f"  students prepared: {index}/50")

    return cohort


# ---------------------------------------------------------------------------
# Attempt simulation
# ---------------------------------------------------------------------------
def _ability(spec: dict, difficulty: str) -> float:
    value = 0.42 + (spec["cgpa"] - 6.0) * 0.10
    if difficulty == "easy":
        value += 0.18
    elif difficulty == "hard":
        value -= 0.18
    return max(0.15, min(0.92, value))


def _response_for(question, rng: random.Random, spec: dict) -> str:
    difficulty = question.difficulty.value
    ability = _ability(spec, difficulty)

    if question.type == QuestionType.CODING:
        # Coding is harder than recall: a student who knows the concept still
        # has to get the program exactly right.
        if rng.random() < ability * 0.80:
            title = question.text.splitlines()[0].strip().lower()
            problem = CODING_BY_TITLE.get(title)
            if problem:
                return (
                    problem["python"]
                    if question.language == CodingLanguage.PYTHON
                    else problem["javascript"]
                )
        return (
            'print("__wrong__")'
            if question.language == CodingLanguage.PYTHON
            else 'console.log("__wrong__");'
        )

    if question.type == QuestionType.DESCRIPTIVE:
        return (
            "The key idea is to separate the responsibilities, state the trade-offs "
            "and justify the chosen approach with a concrete example."
        )

    correct = (question.correct_answer or "").strip()
    if question.type == QuestionType.MULTIPLE_SELECT:
        if rng.random() < ability:
            return correct
        expected = {part.strip() for part in correct.split("|") if part.strip()}
        wrong = [option for option in question.options if option not in expected]
        return rng.choice(wrong) if wrong else correct

    if question.type == QuestionType.TRUE_FALSE:
        if rng.random() < ability:
            return correct
        return "false" if correct.lower() == "true" else "true"

    # MCQ
    if rng.random() < ability:
        return correct
    wrong = [option for option in question.options if option != correct]
    return rng.choice(wrong) if wrong else correct


async def _score_pct(attempt, assessment) -> float:
    total = sum(answer.marks_awarded for answer in attempt.answers)
    max_marks = sum(DIFFICULTY_MARKS[answer.difficulty_at_time] for answer in attempt.answers)
    if assessment.format == AssessmentFormat.STANDARDIZED and assessment.question_ids:
        max_marks = assessment.total_marks or max_marks
        total = max(0.0, min(float(total), float(max_marks)))
    return round(100.0 * total / max_marks, 1) if max_marks > 0 else 0.0


async def _run_attempt(
    service: AssessmentService,
    student_user_id: str,
    student_id: str,
    spec: dict,
    assessment,
    *,
    application_id: str | None = None,
    max_answers: int | None = None,
    seed_key: str,
    log=print,
):
    submitted = await service.attempts.find_many(
        {
            "assessment_id": assessment.id,
            "student_id": student_id,
            "status": AttemptStatus.SUBMITTED.value,
        },
        limit=1,
    )
    if submitted:
        return submitted[0]

    attempt, _ = await service.start_attempt(
        student_user_id, assessment.id, application_id=application_id
    )
    rng = random.Random(f"{seed_key}:{student_id}")

    if service._is_standardized(assessment):
        ordered = await service.questions.find_by_ids(assessment.question_ids)
        if max_answers is not None:
            ordered = ordered[:max_answers]
        for question in ordered:
            response = _response_for(question, rng, spec)
            try:
                attempt, _, _, _, _ = await service.submit_answer(
                    student_user_id,
                    attempt.id,
                    attempt.session_token,
                    question.id,
                    response,
                    round(rng.uniform(12, 80), 1),
                )
            except AssessmentError as exc:
                log(f"    skipped question {question.id}: {exc.message}")
        if attempt.status == AttemptStatus.IN_PROGRESS:
            attempt = await service.finish_attempt(
                student_user_id, attempt.id, attempt.session_token
            )
        return attempt

    # Adaptive practice: follow the engine's own next-question pointer.
    answered = 0
    while answered < assessment.question_pool_size:
        if max_answers is not None and answered >= max_answers:
            break
        if not attempt.current_question_id:
            break
        question = await service.questions.get_by_id(attempt.current_question_id)
        if not question:
            break
        response = _response_for(question, rng, spec)
        try:
            attempt, next_question, _, _, _ = await service.submit_answer(
                student_user_id,
                attempt.id,
                attempt.session_token,
                question.id,
                response,
                round(rng.uniform(12, 80), 1),
            )
        except AssessmentError as exc:
            log(f"    skipped question {question.id}: {exc.message}")
            break
        answered += 1
        if attempt.status != AttemptStatus.IN_PROGRESS or next_question is None:
            break

    if attempt.status == AttemptStatus.IN_PROGRESS:
        attempt = await service.finish_attempt(
            student_user_id, attempt.id, attempt.session_token
        )
    return attempt


# ---------------------------------------------------------------------------
# Notifications (data-only; the collection has no service/UI yet)
# ---------------------------------------------------------------------------
async def _notify(
    db: AsyncIOMotorDatabase,
    *,
    key: str,
    user_id: str,
    role: str,
    notification_type: str,
    title: str,
    message: str,
    metadata: dict | None = None,
    created_at: datetime | None = None,
) -> None:
    await db.notifications.update_one(
        {"_id": stable_oid(f"notification:{key}")},
        {
            "$set": {
                "user_id": user_id,
                "role": role,
                "type": notification_type,
                "title": title,
                "message": message,
                "read": False,
                "created_at": created_at or now(),
                "metadata": metadata or {},
                **SYNTHETIC,
            }
        },
        upsert=True,
    )


# ---------------------------------------------------------------------------
# Applications + attempts
# ---------------------------------------------------------------------------
async def _seed_activity(
    db: AsyncIOMotorDatabase,
    cohort: list[tuple[object, object, dict]],
    tpo_user_id: str,
    log=print,
) -> dict:
    drive_service = DriveService(db)
    assessment_service = AssessmentService(db)
    applications = ApplicationRepository(db)
    assessments = AssessmentRepository(db)
    drives = await PlacementDriveRepository(db).find_many(
        {"status": DriveStatus.OPEN.value}, limit=500, sort=[("created_at", 1)]
    )
    drive_index = {drive.id: index for index, drive in enumerate(drives)}
    practice = await assessments.find_one({"title": "Placement Drive Mock - Practice"})
    adaptive_practice = await assessments.find_one(
        {"title": "Full-Stack Placement Readiness - Practice"}
    )

    application_count = 0
    drive_attempts = 0
    practice_attempts = 0

    for position, (user, student, spec) in enumerate(cohort):
        index = spec["index"]

        # Every student takes the standardized practice mock once. This is the
        # attempt that guarantees real knowledge states for all 50 students
        # and exercises hidden coding tests for every account.
        if practice:
            try:
                attempt = await _run_attempt(
                    assessment_service,
                    user.id,
                    student.id,
                    spec,
                    practice,
                    # A quarter of the cohort answers the whole paper, which
                    # includes the coding question in the final section, so
                    # seeded data proves hidden-test grading works end to end.
                    max_answers=20 if index % 4 == 0 else 10 + (index % 7),
                    seed_key=f"practice:{practice.id}",
                    log=log,
                )
                practice_attempts += 1
                score = await _score_pct(attempt, practice)
                await _notify(
                    db,
                    key=f"practice-result:{spec['email']}:{practice.id}",
                    user_id=user.id,
                    role="student",
                    notification_type="assessment_result",
                    title="Practice mock result available",
                    message=(
                        f"Your placement mock score is {score:.1f}%. "
                        "Review the section breakdown to plan your next practice."
                    ),
                    metadata={
                        "assessment_id": practice.id,
                        "attempt_id": attempt.id,
                        "score_pct": score,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - one student must not abort the seed
                log(f"  WARN practice attempt failed for {spec['email']}: {exc}")

        # A third of the cohort also tries an adaptive practice paper.
        if adaptive_practice and index % 3 == 0:
            try:
                await _run_attempt(
                    assessment_service,
                    user.id,
                    student.id,
                    spec,
                    adaptive_practice,
                    max_answers=6 + (index % 4),
                    seed_key=f"practice:{adaptive_practice.id}",
                    log=log,
                )
                practice_attempts += 1
            except Exception as exc:  # noqa: BLE001
                log(f"  WARN adaptive attempt failed for {spec['email']}: {exc}")

        eligible = [
            drive
            for drive in drives
            if drive_service._check_eligibility(student, drive)[0]
        ]
        if not eligible:
            log(f"  WARN no eligible drives for {spec['email']}")
            continue

        count = min(len(eligible), 3 + (index % 4))
        start = (index * 5) % len(eligible)
        selected = [eligible[(start + offset) % len(eligible)] for offset in range(count)]

        for drive in selected:
            try:
                application = await drive_service.apply_to_drive(user.id, drive.id)
                application_count += 1
            except DriveError:
                application = await applications.get_existing(drive.id, student.id)
            if not application:
                continue

            should_attempt = (index * 11 + drive_index[drive.id] * 7) % 10 < 6
            if should_attempt and drive.required_assessment_id:
                assessment = await assessments.get_by_id(
                    str(drive.required_assessment_id)
                )
                if not assessment or assessment.status != AssessmentPublishStatus.PUBLISHED:
                    continue
                try:
                    await _run_attempt(
                        assessment_service,
                        user.id,
                        student.id,
                        spec,
                        assessment,
                        application_id=application.id,
                        # Same rule as practice: a slice of students completes
                        # the paper so the coding question is actually graded.
                        max_answers=(
                            20
                            if (index + drive_index[drive.id]) % 5 == 0
                            else 11 + ((index + drive_index[drive.id]) % 8)
                        ),
                        seed_key=f"drive:{drive.id}",
                        log=log,
                    )
                    drive_attempts += 1
                except Exception as exc:  # noqa: BLE001
                    log(
                        f"  WARN drive attempt failed for {spec['email']} / "
                        f"{drive.job_title}: {exc}"
                    )
                    continue

            refreshed = await applications.get_by_id(application.id)
            if not refreshed or refreshed.status != ApplicationStatus.APPLIED.value:
                continue

            # Decide a placement outcome from the real assessment result.
            if refreshed.assessment_status == AssessmentStatus.PASSED.value:
                if (index + drive_index[drive.id]) % 3 == 0:
                    try:
                        await drive_service.update_application_status(
                            tpo_user_id,
                            drive.id,
                            refreshed.id,
                            ApplicationStatus.SHORTLISTED.value,
                            actor_role="tpo",
                        )
                        await _notify(
                            db,
                            key=f"app-shortlisted:{refreshed.id}",
                            user_id=user.id,
                            role="student",
                            notification_type="application_status",
                            title=f"Shortlisted for {drive.job_title}",
                            message=(
                                f"You have been shortlisted by the placement team for "
                                f"{drive.job_title}."
                            ),
                            metadata={
                                "drive_id": drive.id,
                                "application_id": refreshed.id,
                                "status": "shortlisted",
                            },
                        )
                    except DriveError as exc:
                        log(f"  WARN shortlist failed for {refreshed.id}: {exc.message}")
            elif refreshed.assessment_status == AssessmentStatus.FAILED.value:
                if (index + drive_index[drive.id]) % 2 == 0:
                    try:
                        await drive_service.update_application_status(
                            tpo_user_id,
                            drive.id,
                            refreshed.id,
                            ApplicationStatus.REJECTED.value,
                            rejection_reasons=[RejectionReason.LOW_ASSESSMENT_SCORE.value],
                            rejection_note=(
                                "Assessment score below the drive's minimum requirement."
                            ),
                            actor_role="tpo",
                        )
                        await _notify(
                            db,
                            key=f"app-rejected:{refreshed.id}",
                            user_id=user.id,
                            role="student",
                            notification_type="application_status",
                            title=f"Application update for {drive.job_title}",
                            message=(
                                "Your application was not taken forward because the "
                                "assessment score did not meet the drive requirement."
                            ),
                            metadata={
                                "drive_id": drive.id,
                                "application_id": refreshed.id,
                                "status": "rejected",
                            },
                        )
                    except DriveError as exc:
                        log(f"  WARN rejection failed for {refreshed.id}: {exc.message}")
            elif refreshed.status == ApplicationStatus.APPLIED.value and spec["cgpa"] >= 8.5:
                if (index * 3 + drive_index[drive.id]) % 7 == 0:
                    try:
                        await drive_service.update_application_status(
                            tpo_user_id,
                            drive.id,
                            refreshed.id,
                            ApplicationStatus.SHORTLISTED.value,
                            actor_role="tpo",
                        )
                    except DriveError:
                        pass

        if position % 10 == 0:
            log(
                f"  activity: {position + 1}/50 students, "
                f"{application_count} applications, {drive_attempts} drive attempts"
            )

    # Welcome notification for every student (idempotent).
    for user, _student, spec in cohort:
        await _notify(
            db,
            key=f"welcome:{spec['email']}",
            user_id=user.id,
            role="student",
            notification_type="welcome",
            title="Welcome to PLACER",
            message=(
                "Complete your profile, upload a resume and start with a practice "
                "assessment to see your readiness score."
            ),
            created_at=now() - timedelta(days=30),
        )

    # One activity digest per drive for the TPO.
    for drive in drives:
        total = await db.applications.count_documents({"drive_id": drive.id})
        shortlisted = await db.applications.count_documents(
            {"drive_id": drive.id, "status": ApplicationStatus.SHORTLISTED.value}
        )
        await _notify(
            db,
            key=f"tpo-drive:{drive.id}",
            user_id=tpo_user_id,
            role="tpo",
            notification_type="drive_activity",
            title=f"Drive activity: {drive.job_title}",
            message=f"{total} application(s), {shortlisted} shortlisted.",
            metadata={"drive_id": drive.id, "applications": total, "shortlisted": shortlisted},
        )

    return {
        "applications": application_count,
        "drive_attempts": drive_attempts,
        "practice_attempts": practice_attempts,
    }


async def _seed_initial_knowledge(
    db: AsyncIOMotorDatabase, cohort: list[tuple[object, object, dict]]
) -> None:
    """Give every student a starting mastery snapshot for their top skills.

    Attempts have already created real knowledge states; this only fills in
    skills the student has not been assessed on yet, so dashboards are not
    empty for a fresh account.
    """
    operations = []
    for user, student, spec in cohort:
        for position, skill in enumerate(spec["skills"][:6]):
            mastery = 35.0 + ((spec["index"] * 13 + position * 7) % 35)
            operations.append(
                UpdateOne(
                    {"student_id": student.id, "skill_tag": skill},
                    {
                        "$setOnInsert": {
                            "student_id": student.id,
                            "skill_tag": skill,
                            "mastery_pct": mastery,
                            "confidence": 0.15,
                            "attempts_count": 0,
                            "last_updated": now(),
                            "history": [
                                {"date": now().isoformat(), "mastery_pct": mastery}
                            ],
                            **SYNTHETIC,
                        }
                    },
                    upsert=True,
                )
            )
    if operations:
        await db.knowledge_states.bulk_write(operations, ordered=False)


async def seed_cohort(
    db: AsyncIOMotorDatabase, tpo_user_id: str, log=print
) -> dict:
    log("Students, profiles and resumes:")
    cohort = await _ensure_students(db, log=log)
    log("\nApplications and assessment attempts:")
    activity = await _seed_activity(db, cohort, tpo_user_id, log=log)
    await _seed_initial_knowledge(db, cohort)

    students = await db.students.count_documents({})
    applications = await db.applications.count_documents({})
    attempts = await db.assessment_attempts.count_documents({})
    submitted = await db.assessment_attempts.count_documents({"status": "submitted"})
    knowledge = await db.knowledge_states.count_documents({})
    notifications = await db.notifications.count_documents({})
    resumes = await db.resumes.count_documents({})
    log(
        f"\nCohort: students={students}, resumes={resumes}, applications={applications}, "
        f"attempts={attempts} (submitted={submitted}), knowledge_states={knowledge}, "
        f"notifications={notifications}"
    )
    return {
        "students": students,
        "resumes": resumes,
        "applications": applications,
        "attempts": attempts,
        "submitted_attempts": submitted,
        "knowledge_states": knowledge,
        "notifications": notifications,
        **activity,
    }
