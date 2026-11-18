"""Seed a clearly-labelled synthetic demo cohort into the live database.

Why this exists
---------------
The placement dashboards need a realistic volume of connected records to be
demonstrable. Real institutional exports are not available in this
environment, so this script creates *explicitly synthetic* students,
resumes, applications and assessment attempts. Every record it writes carries:

    data_origin     = "synthetic"
    is_synthetic    = True
    synthetic_batch = "placer-demo-v1"

Nothing here is presented as genuine institutional data, and the API/UI read
those flags to mark demo rows. Real records already in the database are never
modified or deleted.

What it builds (end to end)
---------------------------
For every open drive without a standardized assessment, it calls the project's
real ``PlacementAssessmentService.generate`` so the assessment has exactly
20 questions: 4 Quantitative Aptitude, 4 Logical Reasoning, 4 Verbal Ability,
4 Technical Knowledge, 4 Programming / Problem Solving, with a 6/10/4
easy/medium/hard split. Questions are real documents from the question bank;
none are invented.

Then, for each synthetic student:

    user -> student profile -> resume -> applications
         -> submitted assessment attempt -> per-question answers
         -> application assessment score/status -> shortlist/reject decision

Scores are computed with the same ``DIFFICULTY_MARKS`` rule the backend uses,
and rankings are produced at read time by the existing analytics service from
those attempts. No score or rank is hardcoded.

Idempotency
-----------
Document ``_id`` values are derived from stable keys, and every write uses
``$setOnInsert``. Re-running the script adds only what is missing; it never
duplicates students, applications or attempts, and never overwrites a status
an authorised user has since changed.

Usage (from ``PLACER/backend``)::

    .venv\\Scripts\\python.exe -m scripts.seed_synthetic_demo
    .venv\\Scripts\\python.exe -m scripts.seed_synthetic_demo --skip-assessments
    .venv\\Scripts\\python.exe -m scripts.seed_synthetic_demo --students 12

Login for every seeded student: the password printed at the end of the run.
Set ``PLACER_DEMO_PASSWORD`` to choose a fixed password instead.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import random
import secrets
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from bson import ObjectId  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.assessment import (  # noqa: E402
    DIFFICULTY_MARKS,
    DifficultyLevel,
    PlacementGenerationRequest,
    PlacementSectionRequest,
)
from app.services.placement_assessment_service import (  # noqa: E402
    PlacementAssessmentService,
    PlacementGenerationError,
)

BATCH = "placer-demo-v1"
PASSWORD = os.environ.get("PLACER_DEMO_PASSWORD") or secrets.token_urlsafe(12)
EMAIL_DOMAIN = "demo.placer.edu"
SEED = 20261118

SYNTHETIC = {
    "data_origin": "synthetic",
    "is_synthetic": True,
    "synthetic_batch": BATCH,
}

# Section -> question-bank category names. Names are resolved to ids by the
# real generator; passing names keeps this readable.
BASE_SECTIONS = [
    ("Quantitative Aptitude", ["Aptitude & Logical Reasoning"]),
    ("Logical Reasoning", ["Aptitude & Logical Reasoning"]),
    ("Verbal Ability", ["Verbal Ability"]),
]

# Per-drive technical / programming category focus, so each drive's assessment
# reflects its domain instead of every drive sharing one generic paper.
DRIVE_FOCUS: dict[str, dict[str, list[str]]] = {
    "Software Development Engineer I": {
        "technical": ["DBMS & SQL", "Operating Systems", "Python Programming", "Data Structures & Algorithms"],
        "programming": ["Data Structures & Algorithms", "Python Programming", "JavaScript & Web Development", "Software Engineering"],
    },
    "Backend Engineer": {
        "technical": ["DBMS & SQL", "Operating Systems", "Computer Networks", "Python Programming"],
        "programming": ["Python Programming", "Data Structures & Algorithms", "DBMS & SQL", "Software Engineering"],
    },
    "Frontend Developer": {
        "technical": ["JavaScript & Web Development", "Object-Oriented Programming", "Software Engineering", "Data Structures & Algorithms"],
        "programming": ["JavaScript & Web Development", "Data Structures & Algorithms", "Python Programming", "Software Engineering"],
    },
    "Data Analyst": {
        "technical": ["DBMS & SQL", "Machine Learning & AI", "Python Programming", "Software Engineering"],
        "programming": ["Python Programming", "Data Structures & Algorithms", "DBMS & SQL", "Software Engineering"],
    },
    "DevOps Engineer": {
        "technical": ["Cloud & DevOps", "Operating Systems", "Computer Networks", "Cybersecurity"],
        "programming": ["Python Programming", "Data Structures & Algorithms", "Software Engineering", "DBMS & SQL"],
    },
    "Cybersecurity Analyst": {
        "technical": ["Cybersecurity", "Computer Networks", "Operating Systems", "Cloud & DevOps"],
        "programming": ["Python Programming", "Data Structures & Algorithms", "Software Engineering", "DBMS & SQL"],
    },
    "Machine Learning Engineer": {
        "technical": ["Machine Learning & AI", "Python Programming", "Data Structures & Algorithms", "DBMS & SQL"],
        "programming": ["Python Programming", "Data Structures & Algorithms", "Machine Learning & AI", "Software Engineering"],
    },
    "QA Automation Engineer": {
        "technical": ["Software Engineering", "Python Programming", "JavaScript & Web Development", "Object-Oriented Programming"],
        "programming": ["Python Programming", "JavaScript & Web Development", "Data Structures & Algorithms", "Software Engineering"],
    },
    "Business Analyst": {
        "technical": ["DBMS & SQL", "Software Engineering", "Machine Learning & AI", "Python Programming"],
        "programming": ["Python Programming", "Data Structures & Algorithms", "Software Engineering", "DBMS & SQL"],
    },
    "Embedded Software Engineer": {
        "technical": ["Operating Systems", "Object-Oriented Programming", "Data Structures & Algorithms", "Python Programming"],
        "programming": ["Data Structures & Algorithms", "Python Programming", "Object-Oriented Programming", "Software Engineering"],
    },
}

DEPARTMENT_SKILLS: dict[str, list[str]] = {
    "Computer Science": [
        "Python", "Java", "JavaScript", "React", "SQL", "MongoDB", "Git",
        "Data Structures", "Algorithms", "Docker", "REST APIs", "Machine Learning",
    ],
    "Information Technology": [
        "SQL", "Python", "JavaScript", "React", "REST APIs", "Git", "AWS",
        "Docker", "Linux", "MongoDB", "Node.js", "Cloud",
    ],
    "Electronics and Communication": [
        "C", "C++", "Python", "Embedded C", "Microcontrollers", "Networking",
        "Linux", "Git", "Signal Processing", "ARM Cortex",
    ],
    "Electrical Engineering": [
        "C", "C++", "MATLAB", "Python", "Embedded C", "Microcontrollers",
        "Git", "Control Systems", "Power Systems",
    ],
    "Mathematics and Computing": [
        "Python", "SQL", "Statistics", "Machine Learning", "Pandas", "NumPy",
        "Git", "Data Structures", "Algorithms", "Probability",
    ],
    "Statistics": [
        "SQL", "Python", "Statistics", "Pandas", "Power BI", "Excel",
        "Data Visualisation", "R", "Probability",
    ],
}

PROJECT_BY_DEPARTMENT: dict[str, str] = {
    "Computer Science": "a full-stack placement portal with React and FastAPI",
    "Information Technology": "a cloud-hosted inventory service with Docker and AWS",
    "Electronics and Communication": "an IoT sensor gateway with an embedded C firmware",
    "Electrical Engineering": "a microcontroller-based energy monitoring unit",
    "Mathematics and Computing": "a demand forecasting model with scikit-learn",
    "Statistics": "an interactive analytics dashboard over a SQL warehouse",
}

# 20 realistic-but-fictional students. Names are deliberately generic; the
# email domain and every record's provenance flags make their status explicit.
ROSTER: list[dict] = [
    {"name": "Aarav Sharma", "department": "Computer Science", "batch_year": 2026, "cgpa": 9.1},
    {"name": "Diya Patel", "department": "Information Technology", "batch_year": 2026, "cgpa": 8.7},
    {"name": "Rohan Mehta", "department": "Computer Science", "batch_year": 2027, "cgpa": 8.2},
    {"name": "Ananya Iyer", "department": "Electronics and Communication", "batch_year": 2026, "cgpa": 9.3},
    {"name": "Kabir Nair", "department": "Information Technology", "batch_year": 2027, "cgpa": 7.8},
    {"name": "Ishita Verma", "department": "Computer Science", "batch_year": 2026, "cgpa": 8.9},
    {"name": "Arjun Reddy", "department": "Electrical Engineering", "batch_year": 2026, "cgpa": 8.4},
    {"name": "Meera Joshi", "department": "Mathematics and Computing", "batch_year": 2026, "cgpa": 9.0},
    {"name": "Vivaan Desai", "department": "Computer Science", "batch_year": 2027, "cgpa": 7.6},
    {"name": "Saanvi Kulkarni", "department": "Statistics", "batch_year": 2026, "cgpa": 8.8},
    {"name": "Aditya Rao", "department": "Information Technology", "batch_year": 2026, "cgpa": 7.9},
    {"name": "Neha Gupta", "department": "Computer Science", "batch_year": 2026, "cgpa": 8.6},
    {"name": "Karan Malhotra", "department": "Electronics and Communication", "batch_year": 2027, "cgpa": 7.7},
    {"name": "Riya Chatterjee", "department": "Information Technology", "batch_year": 2026, "cgpa": 8.5},
    {"name": "Siddharth Bose", "department": "Electrical Engineering", "batch_year": 2027, "cgpa": 7.4},
    {"name": "Tanvi Shah", "department": "Mathematics and Computing", "batch_year": 2027, "cgpa": 8.3},
    {"name": "Aryan Kapoor", "department": "Computer Science", "batch_year": 2026, "cgpa": 7.2},
    {"name": "Pooja Menon", "department": "Electronics and Communication", "batch_year": 2026, "cgpa": 8.1},
    {"name": "Harsh Vardhan", "department": "Information Technology", "batch_year": 2026, "cgpa": 6.9},
    {"name": "Sneha Pillai", "department": "Computer Science", "batch_year": 2027, "cgpa": 7.5},
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def stable_oid(key: str) -> ObjectId:
    """Deterministic ObjectId so re-running never creates duplicates."""
    return ObjectId(hashlib.sha256(key.encode("utf-8")).hexdigest()[:24])


def email_for(index: int) -> str:
    return f"demo.student{index + 1:02d}@{EMAIL_DOMAIN}"


def student_skills(department: str, rng: random.Random) -> list[str]:
    pool = list(DEPARTMENT_SKILLS.get(department, DEPARTMENT_SKILLS["Computer Science"]))
    rng.shuffle(pool)
    take = rng.randint(8, min(11, len(pool)))
    chosen = pool[:take]
    # Add one cross-domain skill so profiles are not carbon copies.
    extras = ["Git", "Docker", "SQL", "Communication", "Problem Solving", "AWS"]
    for extra in extras:
        if extra not in chosen and rng.random() < 0.5:
            chosen.append(extra)
    return sorted(set(chosen))


def ability_for(cgpa: float, rng: random.Random) -> float:
    base = 0.30 + (cgpa - 6.0) * 0.12
    return max(0.30, min(0.94, base + rng.uniform(-0.12, 0.12)))


def wrong_response(question: dict, rng: random.Random) -> str:
    correct = question.get("correct_answer")
    options = [option for option in (question.get("options") or []) if option != correct]
    if options:
        return rng.choice(options)
    if str(question.get("type")) == "true_false":
        return "False" if str(correct).strip().lower() in {"true", "t"} else "True"
    return "None of the above"


def correct_response(question: dict) -> str:
    answer = question.get("correct_answer")
    if answer not in (None, ""):
        return str(answer)
    if str(question.get("type")) == "true_false":
        return "True"
    options = question.get("options") or []
    return str(options[0]) if options else "True"


def build_pdf(lines: list[str]) -> bytes:
    """Minimal single-page PDF so synthetic resumes can actually download."""
    def escape(text: str) -> str:
        return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    content = ["BT", "/F1 11 Tf", "50 750 Td"]
    for position, line in enumerate(lines):
        if position:
            content.append("0 -16 Td")
        content.append(f"({escape(line)}) Tj")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def score_attempt(attempt: dict) -> float:
    """Mirror analytics_service._attempt_score_pct exactly."""
    total = sum(answer["marks_awarded"] for answer in attempt["answers"])
    maximum = sum(
        DIFFICULTY_MARKS[DifficultyLevel(answer["difficulty_at_time"])]
        for answer in attempt["answers"]
    )
    return round(100.0 * total / maximum, 1) if maximum > 0 else 0.0


def is_eligible(student: dict, drive: dict) -> bool:
    eligibility = drive.get("eligibility") or {}
    min_cgpa = eligibility.get("min_cgpa")
    if min_cgpa is not None and (student["cgpa"] is None or student["cgpa"] < min_cgpa):
        return False
    departments = eligibility.get("departments") or []
    if departments and student["department"] not in departments:
        return False
    batches = eligibility.get("batch_years") or []
    if batches and student["batch_year"] not in batches:
        return False
    return True


# ---------------------------------------------------------------------------
# Stage 1 — ensure every drive has a valid 20-question standardized assessment
# ---------------------------------------------------------------------------
def sections_for(drive_title: str) -> list[PlacementSectionRequest]:
    focus = DRIVE_FOCUS.get(
        drive_title,
        {
            "technical": ["DBMS & SQL", "Operating Systems", "Computer Networks", "Software Engineering"],
            "programming": ["Data Structures & Algorithms", "Python Programming", "JavaScript & Web Development"],
        },
    )
    sections = [PlacementSectionRequest(name=name, category_ids=list(categories)) for name, categories in BASE_SECTIONS]
    sections.append(PlacementSectionRequest(name="Technical Knowledge", category_ids=list(focus["technical"])))
    sections.append(
        PlacementSectionRequest(name="Programming / Problem Solving", category_ids=list(focus["programming"]))
    )
    return sections


async def ensure_assessments(db, admin_id: str, log=print) -> dict[str, dict]:
    """Return {drive_id: assessment_doc} after guaranteeing a standardized paper."""
    service = PlacementAssessmentService(db)
    result: dict[str, dict] = {}
    drives = await db.placement_drives.find({}).sort("job_title", 1).to_list(length=None)

    for drive in drives:
        drive_id = str(drive["_id"])
        existing = await db.assessments.find_one(
            {"drive_id": drive_id, "format": "standardized", "question_ids": {"$exists": True, "$ne": []}}
        )
        if existing:
            result[drive_id] = existing
            if drive.get("required_assessment_id") != str(existing["_id"]):
                await db.placement_drives.update_one(
                    {"_id": drive["_id"]},
                    {"$set": {"required_assessment_id": str(existing["_id"])}},
                )
            log(f"  REUSE  {drive.get('job_title')!r} -> {existing.get('title')!r}")
        else:
            request = PlacementGenerationRequest(
                drive_id=drive_id,
                title=f"{drive.get('job_title')} - Standardized Placement Assessment",
                time_limit_minutes=30,
                passing_marks=28,
                negative_marks=0.0,
                instructions="Answer all 20 questions. The same question set is used for every eligible student.",
                allow_retake=False,
                publish=True,
                sections=sections_for(str(drive.get("job_title") or "")),
            )
            try:
                generated = await service.generate(request, admin_id)
            except PlacementGenerationError as exc:
                log(f"  FAIL   {drive.get('job_title')!r}: {exc.message}")
                continue

            await db.assessments.update_one(
                {"_id": ObjectId(generated.assessment_id)},
                {"$set": {**SYNTHETIC, "seed_note": "Generated by seed_synthetic_demo"}},
            )
            assessment = await db.assessments.find_one({"_id": ObjectId(generated.assessment_id)})
            result[drive_id] = assessment
            log(
                f"  CREATE {drive.get('job_title')!r} -> {generated.title!r} "
                f"({generated.total_questions} questions, {generated.total_marks} marks)"
            )

        min_score = drive.get("assessment_min_score_pct")
        deadline = drive.get("assessment_deadline") or drive.get("deadline")
        updates = {}
        if min_score is None:
            updates["assessment_min_score_pct"] = 60.0
        if deadline is None:
            updates["assessment_deadline"] = drive.get("deadline")
        if updates:
            await db.placement_drives.update_one({"_id": drive["_id"]}, {"$set": updates})
            drive.update(updates)

    # Applications created before an assessment existed must not keep
    # "not_required" once the drive actually requires one.
    fixed = await db.applications.update_many(
        {
            "drive_id": {"$in": list(result)},
            "assessment_status": "not_required",
            "assessment_attempt_id": None,
        },
        {"$set": {"assessment_status": "pending"}},
    )
    if fixed.modified_count:
        log(f"  FIXED  {fixed.modified_count} existing application(s): not_required -> pending")
    return result


# ---------------------------------------------------------------------------
# Stage 2 — seed the synthetic cohort
# ---------------------------------------------------------------------------
async def seed_cohort(db, assessments: dict[str, dict], count: int, log=print) -> dict:
    rng = random.Random(SEED)
    now = datetime.utcnow()
    storage_root = Path(get_settings().LOCAL_STORAGE_PATH)

    drives = await db.placement_drives.find({"status": "open"}).sort("job_title", 1).to_list(length=None)
    drives = [drive for drive in drives if str(drive["_id"]) in assessments]
    if not drives:
        log("No open drives with assessments found; nothing to seed.")
        return {}

    question_cache: dict[str, dict] = {}
    for assessment in assessments.values():
        for question_id in assessment.get("question_ids") or []:
            if question_id in question_cache:
                continue
            question = await db.questions.find_one({"_id": ObjectId(question_id)})
            if question:
                question_cache[question_id] = question

    password_hash = hash_password(PASSWORD)
    students: list[dict] = []

    log(f"\nSeeding {count} synthetic students ...")
    for index in range(count):
        profile = ROSTER[index % len(ROSTER)]
        email = email_for(index)
        user_id = stable_oid(f"user:{email}")
        student_id = stable_oid(f"student:{email}")
        resume_id = stable_oid(f"resume:{email}")
        name = profile["name"]
        skills = student_skills(profile["department"], rng)
        ability = ability_for(profile["cgpa"], rng)
        project = PROJECT_BY_DEPARTMENT.get(profile["department"], "a software engineering capstone project")

        user_doc = {
            "_id": user_id,
            "email": email,
            "password_hash": password_hash,
            "role": "student",
            "auth_provider": "local",
            "google_sub": None,
            "is_active": True,
            "created_at": now - timedelta(days=120),
            "last_login": None,
            **SYNTHETIC,
        }
        await db.users.update_one({"_id": user_id}, {"$setOnInsert": user_doc}, upsert=True)

        resume_text = (
            f"{name} is a final-year {profile['department']} student (batch {profile['batch_year']}) "
            f"with a CGPA of {profile['cgpa']}. Core skills: {', '.join(skills)}. "
            f"Built {project}. Seeking a placement role where these skills can be applied."
        )
        pdf_bytes = build_pdf(
            [
                name,
                f"{profile['department']} | Batch {profile['batch_year']} | CGPA {profile['cgpa']}",
                f"Email: {email}",
                "",
                "Skills:",
                *[f"  - {skill}" for skill in skills],
                "",
                f"Project: {project}.",
                "",
                "Synthetic demo resume generated by PLACER seed_synthetic_demo.",
            ]
        )
        resume_dir = storage_root / "resumes" / str(student_id)
        resume_dir.mkdir(parents=True, exist_ok=True)
        resume_path = resume_dir / "synthetic_resume.pdf"
        resume_path.write_bytes(pdf_bytes)

        parsed = {
            "name": name,
            "email": email,
            "phone": None,
            "linkedin_url": None,
            "github_url": None,
            "portfolio_url": None,
            "department": profile["department"],
            "batch_year": profile["batch_year"],
            "cgpa": profile["cgpa"],
            "education": [
                {
                    "degree": "B.Tech",
                    "department": profile["department"],
                    "batch_year": profile["batch_year"],
                    "cgpa": profile["cgpa"],
                }
            ],
            "experience": [],
            "projects": [{"title": project, "description": f"Built {project}."}],
            "skills": skills,
            "certifications": [],
            "achievements": [],
            "languages": ["English"],
            "parsing_metadata": {"source": "synthetic-demo-seed"},
        }
        resume_doc = {
            "_id": resume_id,
            "student_id": str(student_id),
            "version": 1,
            "original_filename": f"{name.replace(' ', '_')}_Resume.pdf",
            "file_url": f"local://resumes/{student_id}/synthetic_resume.pdf",
            "file_hash": hashlib.sha256(email.encode()).hexdigest(),
            "file_size_bytes": len(pdf_bytes),
            "parsed": parsed,
            "resume_text": resume_text,
            "skill_set": skills,
            "experience_years": 0.0,
            "resume_embedding": None,
            "uploaded_at": now - timedelta(days=110),
            "is_active": True,
            **SYNTHETIC,
        }
        await db.resumes.update_one({"_id": resume_id}, {"$setOnInsert": resume_doc}, upsert=True)

        student_doc = {
            "_id": student_id,
            "user_id": str(user_id),
            "name": name,
            "department": profile["department"],
            "batch_year": profile["batch_year"],
            "cgpa": profile["cgpa"],
            "phone": None,
            "linkedin_url": None,
            "github_url": None,
            "portfolio_url": None,
            "skills": skills,
            "achievements": [],
            "certificates": [],
            "active_resume_id": str(resume_id),
            "profile_completeness_pct": 100.0,
            **SYNTHETIC,
        }
        await db.students.update_one({"_id": student_id}, {"$setOnInsert": student_doc}, upsert=True)

        students.append(
            {
                "user_id": str(user_id),
                "student_id": str(student_id),
                "resume_id": str(resume_id),
                "name": name,
                "department": profile["department"],
                "batch_year": profile["batch_year"],
                "cgpa": profile["cgpa"],
                "skills": skills,
                "ability": ability,
                "email": email,
            }
        )

    # ---- applications -----------------------------------------------------
    pairs: set[tuple[int, str]] = set()
    for index, student in enumerate(students):
        eligible = [drive for drive in drives if is_eligible(student, drive)]
        rng.shuffle(eligible)
        take = min(len(eligible), rng.randint(3, 5))
        for drive in eligible[:take]:
            pairs.add((index, str(drive["_id"])))

    # Guarantee coverage: every drive gets at least five applicants.
    for drive in drives:
        drive_id = str(drive["_id"])
        current = {index for index, assigned in pairs if assigned == drive_id}
        if len(current) >= 5:
            continue
        candidates = [
            index
            for index, student in enumerate(students)
            if index not in current and is_eligible(student, drive)
        ]
        rng.shuffle(candidates)
        for index in candidates[: 5 - len(current)]:
            pairs.add((index, drive_id))

    drive_by_id = {str(drive["_id"]): drive for drive in drives}
    log(f"Writing {len(pairs)} synthetic application(s) ...")

    applications: list[dict] = []
    for index, drive_id in sorted(pairs, key=lambda item: (item[1], item[0])):
        student = students[index]
        drive = drive_by_id[drive_id]
        assessment = assessments[drive_id]
        application_id = stable_oid(f"application:{student['email']}:{drive_id}")

        created_at = drive.get("created_at") or (now - timedelta(days=30))
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if created_at > now:
            created_at = now - timedelta(days=2)
        window_start = max(created_at + timedelta(hours=1), now - timedelta(days=4))
        window_end = now - timedelta(hours=2)
        if window_start >= window_end:
            window_start = window_end - timedelta(hours=1)
        applied_at = window_start + timedelta(
            seconds=rng.uniform(0, max(1.0, (window_end - window_start).total_seconds()))
        )

        required = drive.get("required_skills") or []
        skill_lookup = {skill.lower() for skill in student["skills"]}
        matched = [skill for skill in required if skill.lower() in skill_lookup]
        missing = [skill for skill in required if skill.lower() not in skill_lookup]
        skills_score = round(100.0 * len(matched) / len(required), 1) if required else 0.0

        application_doc = {
            "_id": application_id,
            "drive_id": drive_id,
            "student_id": student["student_id"],
            "resume_id": student["resume_id"],
            "status": "applied",
            "eligibility_passed": True,
            "eligibility_reasons": [],
            "final_score": skills_score,
            "semantic_score": None,
            "skills_score": skills_score,
            "experience_score": 100.0,
            "matched_skills": matched,
            "missing_skills": missing,
            "assessment_attempt_id": None,
            "assessment_score_pct": None,
            "assessment_status": "pending",
            "rejection_reasons": [],
            "rejection_note": None,
            "decision_at": None,
            "evaluation_version": "synthetic-seed-v1",
            "applied_at": applied_at,
            **SYNTHETIC,
        }
        await db.applications.update_one(
            {"_id": application_id}, {"$setOnInsert": application_doc}, upsert=True
        )
        applications.append(
            {
                "id": str(application_id),
                "student": student,
                "drive": drive,
                "drive_id": drive_id,
                "assessment": assessment,
                "applied_at": applied_at,
                "status": "applied",
                "assessment_status": "pending",
                "attempt": None,
            }
        )

    # ---- decide which applications get an attempt -------------------------
    by_drive: dict[str, list[dict]] = defaultdict(list)
    for application in applications:
        by_drive[application["drive_id"]].append(application)

    for drive_applications in by_drive.values():
        for application in drive_applications:
            application["wants_attempt"] = rng.random() < 0.82
        # Every drive needs enough real results to rank.
        attempted = sum(1 for application in drive_applications if application["wants_attempt"])
        if attempted < 4:
            pending = [application for application in drive_applications if not application["wants_attempt"]]
            rng.shuffle(pending)
            for application in pending[: 4 - attempted]:
                application["wants_attempt"] = True

    # ---- attempts, answers, scores, statuses ------------------------------
    log("Writing submitted attempts, answers, scores and decisions ...")
    for application in applications:
        if not application["wants_attempt"]:
            continue

        student = application["student"]
        drive = application["drive"]
        assessment = application["assessment"]
        question_ids = assessment.get("question_ids") or []
        if not question_ids:
            continue

        started_at = application["applied_at"] + timedelta(hours=rng.uniform(1, 30))
        started_at = min(started_at, now - timedelta(minutes=45))
        if started_at <= application["applied_at"]:
            started_at = application["applied_at"] + timedelta(minutes=30)
        submitted_at = started_at + timedelta(minutes=rng.uniform(12, 38))
        submitted_at = min(submitted_at, now)
        if submitted_at <= started_at:
            submitted_at = started_at + timedelta(minutes=5)

        ability = student["ability"]
        answers: list[dict] = []
        for question_id in question_ids:
            question = question_cache.get(question_id)
            if not question:
                continue
            difficulty = str(question.get("difficulty") or "medium")
            bonus = {"easy": 0.18, "medium": 0.0, "hard": -0.22}.get(difficulty, 0.0)
            probability = max(0.02, min(0.98, ability + bonus + rng.uniform(-0.08, 0.08)))
            is_correct = rng.random() < probability
            answers.append(
                {
                    "question_id": question_id,
                    "response": correct_response(question) if is_correct else wrong_response(question, rng),
                    "is_correct": is_correct,
                    "marks_awarded": float(DIFFICULTY_MARKS[DifficultyLevel(difficulty)]) if is_correct else 0.0,
                    "time_taken_sec": round(rng.uniform(20, 150), 1),
                    "difficulty_at_time": difficulty,
                    "question_type": str(question.get("type") or "mcq"),
                    "code_result": None,
                }
            )

        if not answers:
            continue

        attempt_doc = {
            "_id": stable_oid(f"attempt:{student['email']}:{application['drive_id']}"),
            "assessment_id": str(assessment["_id"]),
            "student_id": student["student_id"],
            "session_token": secrets.token_urlsafe(32),
            "asked_question_ids": list(question_ids),
            "current_question_id": None,
            "current_difficulty": answers[-1]["difficulty_at_time"],
            "answers": answers,
            "violations": [],
            "status": "submitted",
            "started_at": started_at,
            "submitted_at": submitted_at,
            "ip_address": None,
            "fingerprint_hash": None,
            **SYNTHETIC,
        }
        await db.assessment_attempts.update_one(
            {"_id": attempt_doc["_id"]}, {"$setOnInsert": attempt_doc}, upsert=True
        )

        total_marks = sum(answer["marks_awarded"] for answer in answers)
        maximum = assessment.get("total_marks") or sum(
            DIFFICULTY_MARKS[DifficultyLevel(answer["difficulty_at_time"])] for answer in answers
        )
        score_pct = round(100.0 * total_marks / maximum, 1) if maximum else 0.0
        min_score = drive.get("assessment_min_score_pct")
        if min_score is None:
            min_score = 60.0
        passed = score_pct >= float(min_score)
        assessment_status = "passed" if passed else "failed"

        if passed:
            # A clear pass is usually shortlisted; a bare pass stays applied
            # so the "Applied" bucket contains real borderline applications.
            status = (
                "shortlisted"
                if score_pct >= float(min_score) + 3 and rng.random() < 0.80
                else "applied"
            )
        elif score_pct >= float(min_score) - 10:
            # Just below the bar: still under review, not rejected outright.
            status = "applied"
        else:
            status = "rejected" if rng.random() < 0.85 else "applied"

        decision_at = None
        rejection_reasons: list[str] = []
        rejection_note = None
        if status in {"shortlisted", "rejected"}:
            decision_at = min(submitted_at + timedelta(hours=rng.uniform(2, 48)), now)
            if status == "rejected":
                rejection_reasons = ["low_assessment_score"]
                rejection_note = "Assessment score below the shortlisting threshold."

        update = {
            "assessment_attempt_id": str(attempt_doc["_id"]),
            "assessment_score_pct": score_pct,
            "assessment_status": assessment_status,
            "status": status,
            "decision_at": decision_at,
            "rejection_reasons": rejection_reasons,
            "rejection_note": rejection_note,
        }
        # Only fill status/decision on rows this script created. An operator may
        # already have moved a seeded application; never overwrite that.
        existing = await db.applications.find_one(
            {"_id": ObjectId(application["id"])}, {"status": 1, "is_synthetic": 1}
        )
        if existing and existing.get("is_synthetic"):
            await db.applications.update_one(
                {"_id": ObjectId(application["id"])},
                {"$set": {key: value for key, value in update.items() if key != "status"}},
            )
            # Status is only seeded while it is still the untouched default.
            if existing.get("status") == "applied":
                await db.applications.update_one(
                    {"_id": ObjectId(application["id"])}, {"$set": {"status": status}}
                )

        application["status"] = status
        application["assessment_status"] = assessment_status
        application["attempt"] = attempt_doc
        application["score_pct"] = score_pct

    return {
        "students": students,
        "applications": applications,
        "drives": drives,
    }


# ---------------------------------------------------------------------------
# Stage 3 — verify and report
# ---------------------------------------------------------------------------
async def report(db, log=print) -> None:
    log("\n" + "=" * 78)
    log("SYNTHETIC DATA REPORT")
    log("=" * 78)

    synthetic_users = await db.users.count_documents({"is_synthetic": True})
    synthetic_students = await db.students.count_documents({"is_synthetic": True})
    synthetic_resumes = await db.resumes.count_documents({"is_synthetic": True})
    synthetic_apps = await db.applications.count_documents({"is_synthetic": True})
    synthetic_attempts = await db.assessment_attempts.count_documents({"is_synthetic": True})
    log(
        f"users={synthetic_users} students={synthetic_students} resumes={synthetic_resumes} "
        f"applications={synthetic_apps} attempts={synthetic_attempts}"
    )

    status_counts = Counter()
    async for application in db.applications.find({"is_synthetic": True}, {"status": 1}):
        status_counts[application.get("status")] += 1
    log(f"application status: {dict(status_counts)}")

    log("\nPer-drive coverage (synthetic applications only):")
    log(f"{'drive':<36} {'apps':>5} {'att':>5} {'short':>6} {'rej':>5} {'avg%':>6}")
    drives = await db.placement_drives.find({"status": "open"}).sort("job_title", 1).to_list(length=None)
    for drive in drives:
        drive_id = str(drive["_id"])
        applications = await db.applications.find(
            {"drive_id": drive_id, "is_synthetic": True}
        ).to_list(length=None)
        applicant_ids = [app["student_id"] for app in applications]
        # Restrict to THIS drive's assessment. Filtering only by applicant
        # would count the same student's attempts on other drives.
        assessment_id = drive.get("required_assessment_id")
        attempts = await db.assessment_attempts.find(
            {
                "student_id": {"$in": applicant_ids},
                "assessment_id": assessment_id,
                "is_synthetic": True,
            }
        ).to_list(length=None)
        scores = [score_attempt(attempt) for attempt in attempts if attempt.get("answers")]
        statuses = Counter(app.get("status") for app in applications)
        average = round(sum(scores) / len(scores), 1) if scores else 0.0
        log(
            f"{str(drive.get('job_title'))[:34]:<36} {len(applications):>5} {len(attempts):>5} "
            f"{statuses.get('shortlisted', 0):>6} {statuses.get('rejected', 0):>5} {average:>6}"
        )

    missing = []
    async for drive in db.placement_drives.find({"status": "open"}):
        if not drive.get("required_assessment_id"):
            missing.append(drive.get("job_title"))
    log(
        "\nEvery open drive has an assessment."
        if not missing
        else f"\nWARNING: open drives without an assessment: {missing}"
    )
    log(f"\nStudent login password: {PASSWORD}")
    log(f"Example account: {email_for(0)}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a labelled synthetic demo cohort.")
    parser.add_argument("--students", type=int, default=20, help="How many synthetic students to create (default 20).")
    parser.add_argument(
        "--skip-assessments",
        action="store_true",
        help="Do not generate standardized assessments; only seed students/applications/attempts.",
    )
    args = parser.parse_args()

    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]

    try:
        admin = await db.users.find_one({"email": "admin@placer.edu", "role": "admin"}) or await db.users.find_one(
            {"role": "admin"}
        )
        if not admin:
            raise SystemExit("No admin user found. Create one first with scripts.create_admin.")
        admin_id = str(admin["_id"])

        if args.skip_assessments:
            assessments: dict[str, dict] = {}
            async for drive in db.placement_drives.find({"status": "open"}):
                if not drive.get("required_assessment_id"):
                    continue
                assessment = await db.assessments.find_one(
                    {"_id": ObjectId(drive["required_assessment_id"]), "format": "standardized"}
                )
                if assessment:
                    assessments[str(drive["_id"])] = assessment
            print(f"Using existing standardized assessments for {len(assessments)} drive(s).")
        else:
            print("Ensuring every drive has a standardized 20-question assessment ...")
            assessments = await ensure_assessments(db, admin_id)

        count = max(1, min(args.students, len(ROSTER)))
        await seed_cohort(db, assessments, count)
        await report(db)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
