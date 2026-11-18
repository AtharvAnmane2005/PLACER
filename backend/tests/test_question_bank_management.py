"""Question bank management, Excel/CSV import/export, templates and the
standardized 20-question placement assessment flow.

All records used here are created through the real API — no fixtures invent
question content, and the generator must fail when the bank is insufficient.
"""
import csv
import io
from datetime import datetime, timedelta

import pytest
from openpyxl import Workbook, load_workbook

from app.services.assessment_selection_service import allocate_difficulty_slots
from tests.pdf_builder import build_test_pdf

MINIMAL_PDF_BYTES = build_test_pdf(["Test Student", "test@college.edu", "Skills: Python"])


# ---------------------------------------------------------------------------
# Helpers (mirrors the conventions in test_assessments.py)
# ---------------------------------------------------------------------------
async def _admin(client, email="qbm.admin@college.edu"):
    from app.core import database as db_module
    from app.core.security import hash_password

    await db_module.mongodb.db.users.insert_one(
        {
            "email": email,
            "password_hash": hash_password("StrongPass123"),
            "role": "admin",
            "auth_provider": "local",
            "is_active": True,
        }
    )
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


async def _student(client, email="qbm.student@college.edu"):
    await client.post(
        "/api/v1/auth/register/student",
        json={
            "email": email,
            "password": "StrongPass123",
            "name": "QBM Student",
            "department": "CS",
            "batch_year": 2026,
        },
    )
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


async def _tpo(client, email="qbm.tpo@college.edu"):
    await client.post(
        "/api/v1/auth/register/tpo",
        json={"email": email, "password": "StrongPass123", "name": "QBM TPO", "department_scope": []},
    )
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _category(client, admin_token, name):
    response = await client.post(
        "/api/v1/questions/categories", headers=_auth(admin_token), json={"name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _question(client, admin_token, category_id, difficulty, text, *, type="mcq", correct="A", topic=None, skill=None, marks=None):
    payload = {
        "category_id": category_id,
        "skill_tags": [skill] if skill else [],
        "difficulty": difficulty,
        "type": type,
        "text": text,
        "options": ["A", "B", "C", "D"],
        "correct_answer": correct,
        "topic": topic,
        "skill": skill,
        "marks": marks,
    }
    response = await client.post("/api/v1/questions", headers=_auth(admin_token), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _drive(client, tpo_token, title="QBM Drive"):
    payload = {
        "company_name": "QBM Corp",
        "job_title": title,
        "description": "Hiring",
        "jd_text": "We need engineers.",
        "required_skills": ["Python"],
        "eligibility": {},
        "deadline": (datetime.utcnow() + timedelta(days=30)).isoformat(),
        "selection_process": [],
    }
    response = await client.post("/api/v1/drives", headers=_auth(tpo_token), json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _apply(client, student_token, drive_id):
    pdf = MINIMAL_PDF_BYTES
    await client.post(
        "/api/v1/resumes",
        headers=_auth(student_token),
        files={"file": ("resume.pdf", pdf, "application/pdf")},
    )
    response = await client.post(f"/api/v1/drives/{drive_id}/apply", headers=_auth(student_token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


# Section -> (category name, easy, medium, hard) matching the deterministic
# 6/10/4 allocation for five sections of four questions.
SECTION_PLAN = [
    ("Quantitative Aptitude", "Aptitude & Logical Reasoning", 2, 2, 0),
    ("Logical Reasoning", "Aptitude & Logical Reasoning", 1, 2, 1),
    ("Verbal Ability", "Verbal Ability", 1, 2, 1),
    ("Technical Knowledge", "DBMS & SQL", 1, 2, 1),
    ("Programming / Problem Solving", "Data Structures & Algorithms", 1, 2, 1),
]


async def _seed_bank(client, admin_token, prefix="QBM"):
    category_ids = {}
    created = {}
    for section, category_name, easy, medium, hard in SECTION_PLAN:
        if category_name not in category_ids:
            category_ids[category_name] = await _category(client, admin_token, category_name)
        category_id = category_ids[category_name]
        made = []
        for difficulty, count in (("easy", easy), ("medium", medium), ("hard", hard)):
            for index in range(count):
                question = await _question(
                    client,
                    admin_token,
                    category_id,
                    difficulty,
                    f"{prefix} {section} {difficulty} {index}?",
                    topic=section,
                    skill=section.split()[0],
                    marks=3,
                )
                made.append(question)
        created[section] = made
    return created


async def _generate(
    client,
    admin_token,
    drive_id,
    *,
    publish=True,
    negative_marks=0.0,
    allow_retake=False,
    title=None,
    template_id=None,
):
    payload = {
        "drive_id": drive_id,
        "title": title,
        "time_limit_minutes": 30,
        "passing_marks": 30,
        "negative_marks": negative_marks,
        "allow_retake": allow_retake,
        "publish": publish,
    }
    if template_id:
        payload["template_id"] = template_id
        # Let the saved template supply these values.
        for key in ("title", "time_limit_minutes", "passing_marks", "negative_marks", "allow_retake"):
            payload.pop(key)
    response = await client.post(
        "/api/v1/assessments/placement/generate", headers=_auth(admin_token), json=payload
    )
    return response


def test_difficulty_allocation_is_exact_and_balanced():
    allocated = allocate_difficulty_slots(
        [4, 4, 4, 4, 4], {"easy": 6, "medium": 10, "hard": 4}
    )
    assert [len(section) for section in allocated] == [4] * 5
    flat = [difficulty.value for section in allocated for difficulty in section]
    assert flat.count("easy") == 6
    assert flat.count("medium") == 10
    assert flat.count("hard") == 4


# ---------------------------------------------------------------------------
# Question CRUD / search / stats / status / duplicates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_question_search_stats_status_and_duplicate_prevention(client):
    admin = await _admin(client, "qbm.crud.admin@college.edu")
    category_id = await _category(client, admin, "CRUD")

    first = await _question(client, admin, category_id, "easy", "Unique bank question about trees?", topic="Trees", skill="DSA")
    second = await _question(client, admin, category_id, "hard", "Another question about graphs?", topic="Graphs")

    stats = await client.get("/api/v1/questions/stats", headers=_auth(admin))
    assert stats.status_code == 200
    assert stats.json()["total"] == 2
    assert stats.json()["by_difficulty"]["easy"] == 1

    search = await client.get(
        "/api/v1/questions?search=trees&difficulty=easy&topic=Trees", headers=_auth(admin)
    )
    assert search.status_code == 200
    assert [row["id"] for row in search.json()] == [first["id"]]

    duplicate = await client.post(
        "/api/v1/questions",
        headers=_auth(admin),
        json={
            "category_id": category_id,
            "difficulty": "easy",
            "type": "mcq",
            "text": "Unique bank question about trees?",
            "options": ["A", "B"],
            "correct_answer": "A",
        },
    )
    assert duplicate.status_code == 409

    deactivated = await client.patch(
        f"/api/v1/questions/{second['id']}/status?status=inactive", headers=_auth(admin)
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "inactive"
    active_only = await client.get("/api/v1/questions?status=active", headers=_auth(admin))
    assert [row["id"] for row in active_only.json()] == [first["id"]]


@pytest.mark.asyncio
async def test_multiple_select_and_true_false_validation(client):
    admin = await _admin(client, "qbm.types.admin@college.edu")
    category_id = await _category(client, admin, "ObjectiveTypes")

    good = await client.post(
        "/api/v1/questions",
        headers=_auth(admin),
        json={
            "category_id": category_id,
            "difficulty": "medium",
            "type": "multiple_select",
            "text": "Which are prime?",
            "options": ["2", "3", "4"],
            "correct_answer": "2|3",
        },
    )
    assert good.status_code == 201
    assert good.json()["correct_answer"] == "2|3"

    bad = await client.post(
        "/api/v1/questions",
        headers=_auth(admin),
        json={
            "category_id": category_id,
            "difficulty": "medium",
            "type": "multiple_select",
            "text": "Invalid multiple select?",
            "options": ["2", "3"],
            "correct_answer": "9|10",
        },
    )
    assert bad.status_code == 400

    true_false = await client.post(
        "/api/v1/questions",
        headers=_auth(admin),
        json={
            "category_id": category_id,
            "difficulty": "easy",
            "type": "true_false",
            "text": "The sky is blue.",
            "correct_answer": "True",
        },
    )
    assert true_false.status_code == 201
    assert true_false.json()["options"] == ["True", "False"]


# ---------------------------------------------------------------------------
# CSV / XLSX preview, commit, export
# ---------------------------------------------------------------------------
def _csv_bytes(rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


@pytest.mark.asyncio
async def test_csv_preview_is_read_only_then_commit_inserts_real_rows(client):
    admin = await _admin(client, "qbm.csv.admin@college.edu")
    category_id = await _category(client, admin, "CSVCat")
    from app.core import database as db_module

    before = await db_module.mongodb.db.questions.count_documents({})
    content = _csv_bytes(
        [
            ["Question", "Question Type", "Category", "Difficulty", "Option A", "Option B", "Correct Answer", "Explanation"],
            ["CSV question one?", "mcq", "CSVCat", "easy", "Yes", "No", "Yes", "Because reasons."],
            ["CSV question two?", "mcq", "CSVCat", "medium", "A", "B", "B", "Second explanation."],
        ]
    )
    preview_response = await client.post(
        "/api/v1/questions/import/preview",
        headers=_auth(admin),
        files={"file": ("questions.csv", content, "text/csv")},
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["total_rows"] == 2
    assert preview["valid_rows"] == 2
    assert preview["invalid_rows"] == 0
    assert await db_module.mongodb.db.questions.count_documents({}) == before  # nothing inserted

    commit = await client.post(
        "/api/v1/questions/import/commit",
        headers=_auth(admin),
        json={"questions": [row["question"] for row in preview["rows"]]},
    )
    assert commit.status_code == 200, commit.text
    assert commit.json()["imported"] == 2
    assert await db_module.mongodb.db.questions.count_documents({}) == before + 2

    saved = await client.get("/api/v1/questions?search=CSV question one", headers=_auth(admin))
    assert saved.json()[0]["explanation"] == "Because reasons."


@pytest.mark.asyncio
async def test_csv_preview_reports_row_errors_and_error_report_download(client):
    admin = await _admin(client, "qbm.csvbad.admin@college.edu")
    await _category(client, admin, "KnownCat")
    from app.core import database as db_module

    before = await db_module.mongodb.db.questions.count_documents({})
    content = _csv_bytes(
        [
            ["Question", "Question Type", "Category", "Difficulty", "Option A", "Option B", "Correct Answer"],
            ["Bad category?", "mcq", "UnknownCat", "easy", "A", "B", "A"],
            ["Bad difficulty?", "mcq", "KnownCat", "impossible", "A", "B", "A"],
            ["Good row?", "mcq", "KnownCat", "easy", "A", "B", "A"],
        ]
    )
    response = await client.post(
        "/api/v1/questions/import/preview",
        headers=_auth(admin),
        files={"file": ("bad.csv", content, "text/csv")},
    )
    assert response.status_code == 200
    preview = response.json()
    assert preview["invalid_rows"] == 2
    assert preview["valid_rows"] == 1
    fields = {error["field"] for error in preview["errors"]}
    assert "category" in fields and "difficulty" in fields
    assert await db_module.mongodb.db.questions.count_documents({}) == before

    report = await client.post(
        "/api/v1/questions/import/error-report", headers=_auth(admin), json=preview
    )
    assert report.status_code == 200
    assert "Bad category?" in report.text


@pytest.mark.asyncio
async def test_xlsx_preview_and_real_excel_export(client):
    admin = await _admin(client, "qbm.xlsx.admin@college.edu")
    category_id = await _category(client, admin, "XLSXCat")

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Question", "Question Type", "Category", "Difficulty", "Option A", "Option B", "Correct Answer"])
    sheet.append(["Workbook question?", "mcq", "XLSXCat", "easy", "A", "B", "A"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    preview = await client.post(
        "/api/v1/questions/import/preview",
        headers=_auth(admin),
        files={"file": ("questions.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid_rows"] == 1

    commit = await client.post(
        "/api/v1/questions/import/commit",
        headers=_auth(admin),
        json={"questions": [row["question"] for row in preview.json()["rows"]]},
    )
    assert commit.json()["imported"] == 1

    exported = await client.get("/api/v1/questions/export/excel", headers=_auth(admin))
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/vnd.openxmlformats")
    result = load_workbook(io.BytesIO(exported.content))
    assert result.sheetnames[0] == "Question Bank"
    values = [[cell.value for cell in row] for row in result["Question Bank"].iter_rows()]
    assert "Question" in values[0]
    assert any("Workbook question?" in str(row) for row in values[1:])

    template = await client.get("/api/v1/questions/export/template", headers=_auth(admin))
    assert template.status_code == 200
    assert len(load_workbook(io.BytesIO(template.content)).sheetnames) >= 1


@pytest.mark.asyncio
async def test_spreadsheet_endpoints_are_admin_only(client):
    student = await _student(client, "qbm.spreadsheet.student@college.edu")
    preview = await client.post(
        "/api/v1/questions/import/preview",
        headers=_auth(student),
        files={"file": ("questions.csv", b"Question\nanything", "text/csv")},
    )
    assert preview.status_code == 403
    export = await client.get("/api/v1/questions/export/excel", headers=_auth(student))
    assert export.status_code == 403


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_template_presets_crud_duplicate_and_status(client):
    admin = await _admin(client, "qbm.template.admin@college.edu")
    presets = await client.get("/api/v1/assessments/templates/presets", headers=_auth(admin))
    assert presets.status_code == 200
    keys = {p["key"] for p in presets.json()}
    assert {"technical", "aptitude", "logical_reasoning", "verbal_ability", "programming", "placement_drive_mock", "custom"} <= keys

    payload = next(p["config"] for p in presets.json() if p["key"] == "technical")
    payload["name"] = "My Technical Template"
    created = await client.post("/api/v1/assessments/templates", headers=_auth(admin), json=payload)
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/assessments/templates/{template_id}",
        headers=_auth(admin),
        json={**payload, "name": "Renamed Template", "time_limit_sec": 2400},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed Template"

    duplicate = await client.post(
        f"/api/v1/assessments/templates/{template_id}/duplicate", headers=_auth(admin)
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["name"] == "Renamed Template (copy)"

    deactivated = await client.patch(
        f"/api/v1/assessments/templates/{template_id}/status?status=inactive", headers=_auth(admin)
    )
    assert deactivated.json()["status"] == "inactive"

    deleted = await client.delete(f"/api/v1/assessments/templates/{template_id}", headers=_auth(admin))
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/assessments/templates/{template_id}", headers=_auth(admin))).status_code == 404


@pytest.mark.asyncio
async def test_standardized_template_requires_exact_twenty_and_distribution(client):
    admin = await _admin(client, "qbm.templatebad.admin@college.edu")
    presets = (await client.get("/api/v1/assessments/templates/presets", headers=_auth(admin))).json()
    config = next(p["config"] for p in presets if p["key"] == "placement_drive_mock")
    config["total_questions"] = 19
    response = await client.post("/api/v1/assessments/templates", headers=_auth(admin), json=config)
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Standardized placement assessments
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generation_applies_saved_template_configuration(client):
    admin = await _admin(client, "qbm.templategen.admin@college.edu")
    tpo = await _tpo(client, "qbm.templategen.tpo@college.edu")
    await _seed_bank(client, admin, "TemplateGen")
    drive_id = await _drive(client, tpo, "Template Drive")

    presets = (await client.get("/api/v1/assessments/templates/presets", headers=_auth(admin))).json()
    config = next(p["config"] for p in presets if p["key"] == "placement_drive_mock")
    config.update(
        {
            "name": "Saved Standardized Template",
            "time_limit_sec": 2700,
            "passing_marks": 42,
            "negative_marks": 0.5,
            "allow_retake": True,
            "instructions": "Template supplied instructions.",
        }
    )
    created = await client.post("/api/v1/assessments/templates", headers=_auth(admin), json=config)
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]

    generated = await _generate(client, admin, drive_id, publish=True, template_id=template_id)
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["template_id"] == template_id
    assert body["title"] == "Saved Standardized Template"
    assert body["time_limit_sec"] == 2700
    assert [section["name"] for section in body["sections"]] == [name for name, *_ in SECTION_PLAN]

    listed = await client.get("/api/v1/assessments", headers=_auth(admin))
    assessment = next(item for item in listed.json() if item["id"] == body["assessment_id"])
    assert assessment["passing_marks"] == 42
    assert assessment["negative_marks"] == 0.5
    assert assessment["allow_retake"] is True
    assert assessment["instructions"] == "Template supplied instructions."


@pytest.mark.asyncio
async def test_generation_is_exactly_twenty_with_named_deficits(client):
    admin = await _admin(client, "qbm.deficit.admin@college.edu")
    tpo = await _tpo(client, "qbm.deficit.tpo@college.edu")
    drive_id = await _drive(client, tpo, "Deficit Drive")

    response = await _generate(client, admin, drive_id)
    assert response.status_code == 422
    detail = response.json()["detail"]
    message = str(detail)
    assert "Verbal Ability" in message
    lowered = message.lower()
    assert "easy" in lowered and "medium" in lowered and "hard" in lowered
    assert detail["deficits"]


@pytest.mark.asyncio
async def test_generation_exact_twenty_fixed_set_shared_by_students(client):
    admin = await _admin(client, "qbm.gen.admin@college.edu")
    tpo = await _tpo(client, "qbm.gen.tpo@college.edu")
    await _seed_bank(client, admin, "Gen")
    drive_id = await _drive(client, tpo, "Generation Drive")

    generated = await _generate(client, admin, drive_id)
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["total_questions"] == 20
    assert body["total_marks"] == 60
    assert body["time_limit_sec"] == 1800
    assert body["format"] == "standardized"
    assert [len(section["question_ids"]) for section in body["sections"]] == [4] * 5
    difficulties = [question["difficulty"] for question in body["questions"]]
    assert difficulties.count("easy") == 6
    assert difficulties.count("medium") == 10
    assert difficulties.count("hard") == 4
    generation_ids = [q["id"] for q in body["questions"]]
    assert len(set(generation_ids)) == 20

    # Two eligible students receive the exact same ordered set and duration.
    student_a = await _student(client, "qbm.gen.a@college.edu")
    student_b = await _student(client, "qbm.gen.b@college.edu")
    application_a = await _apply(client, student_a, drive_id)
    application_b = await _apply(client, student_b, drive_id)

    starts = []
    for token, application_id in ((student_a, application_a), (student_b, application_b)):
        start = await client.post(
            f"/api/v1/assessments/{body['assessment_id']}/start",
            headers=_auth(token),
            json={"application_id": application_id},
        )
        assert start.status_code == 201, start.text
        starts.append(start.json())

    for start in starts:
        assert len(start["questions"]) == 20
        assert [q["id"] for q in start["questions"]] == generation_ids
        assert start["time_limit_sec"] == 1800
        assert start["format"] == "standardized"
        assert "correct_answer" not in start["questions"][0]

    # The reload endpoint returns the same answer-key-free set.
    reloaded = await client.get(
        f"/api/v1/assessments/attempts/{starts[0]['attempt_id']}/questions",
        headers=_auth(student_a),
    )
    assert reloaded.status_code == 200
    assert [q["id"] for q in reloaded.json()["questions"]] == generation_ids
    assert "correct_answer" not in reloaded.json()["questions"][0]


@pytest.mark.asyncio
async def test_draft_blocked_retake_rules_answer_changes_and_negative_marking(client):
    admin = await _admin(client, "qbm.flow.admin@college.edu")
    tpo = await _tpo(client, "qbm.flow.tpo@college.edu")
    await _seed_bank(client, admin, "Flow")
    drive_id = await _drive(client, tpo, "Flow Drive")

    draft = await _generate(client, admin, drive_id, publish=False)
    student = await _student(client, "qbm.flow.student@college.edu")
    application_id = await _apply(client, student, drive_id)
    blocked = await client.post(
        f"/api/v1/assessments/{draft.json()['assessment_id']}/start",
        headers=_auth(student),
        json={"application_id": application_id},
    )
    assert blocked.status_code == 403

    published = await _generate(
        client, admin, drive_id, publish=True, negative_marks=1.5, title="Published Flow"
    )
    assessment_id = published.json()["assessment_id"]
    start = await client.post(
        f"/api/v1/assessments/{assessment_id}/start",
        headers=_auth(student),
        json={"application_id": application_id},
    )
    assert start.status_code == 201, start.text
    attempt_id = start.json()["attempt_id"]
    token = start.json()["session_token"]
    questions = start.json()["questions"]

    # Answers outside the fixed set are rejected.
    outsider = await client.post(
        f"/api/v1/assessments/attempts/{attempt_id}/answer",
        headers=_auth(student),
        json={"session_token": token, "question_id": "000000000000000000000000", "response": "A"},
    )
    assert outsider.status_code == 400

    target = questions[0]
    correct_answer = "Yes" if target["type"] == "true_false" else None
    # Our seeded bank is all MCQ with correct answer "A".
    wrong = await client.post(
        f"/api/v1/assessments/attempts/{attempt_id}/answer",
        headers=_auth(student),
        json={"session_token": token, "question_id": target["id"], "response": "B", "time_taken_sec": 10},
    )
    assert wrong.status_code == 200
    assert wrong.json()["marks_awarded"] == -1.5
    assert wrong.json()["attempt_status"] == "in_progress"  # no per-question finalization

    changed = await client.post(
        f"/api/v1/assessments/attempts/{attempt_id}/answer",
        headers=_auth(student),
        json={"session_token": token, "question_id": target["id"], "response": "A", "time_taken_sec": 12},
    )
    assert changed.status_code == 200
    assert changed.json()["marks_awarded"] == 3 or changed.json()["marks_awarded"] == 1 or changed.json()["marks_awarded"] == 5
    assert len(changed.json()["answered_question_ids"]) == 1  # replaced, not duplicated

    # Results before submission must not reveal the answer key.
    pending_results = await client.get(
        f"/api/v1/assessments/attempts/{attempt_id}/results", headers=_auth(student)
    )
    assert all(item["correct_answer"] is None for item in pending_results.json()["answers"])

    finished = await client.post(
        f"/api/v1/assessments/attempts/{attempt_id}/finish",
        headers=_auth(student),
        json={"session_token": token},
    )
    assert finished.status_code == 200
    assert finished.json()["status"] == "submitted"

    submitted_results = await client.get(
        f"/api/v1/assessments/attempts/{attempt_id}/results", headers=_auth(student)
    )
    answer_rows = submitted_results.json()["answers"]
    assert any(item["correct_answer"] for item in answer_rows)
    assert submitted_results.json()["max_possible_marks"] == 60
    assert submitted_results.json()["total_marks"] >= 0  # clamped

    # Retakes are disabled by default.
    second_start = await client.post(
        f"/api/v1/assessments/{assessment_id}/start",
        headers=_auth(student),
        json={"application_id": application_id},
    )
    assert second_start.status_code == 403


@pytest.mark.asyncio
async def test_retake_allowed_and_participation_counts_real_attempts(client):
    admin = await _admin(client, "qbm.retake.admin@college.edu")
    tpo = await _tpo(client, "qbm.retake.tpo@college.edu")
    await _seed_bank(client, admin, "Retake")
    drive_id = await _drive(client, tpo, "Retake Drive")
    generated = await _generate(client, admin, drive_id, allow_retake=True)
    assessment_id = generated.json()["assessment_id"]

    student = await _student(client, "qbm.retake.student@college.edu")
    application_id = await _apply(client, student, drive_id)
    first = await client.post(
        f"/api/v1/assessments/{assessment_id}/start",
        headers=_auth(student),
        json={"application_id": application_id},
    )
    assert first.status_code == 201
    first_body = first.json()
    await client.post(
        f"/api/v1/assessments/attempts/{first_body['attempt_id']}/finish",
        headers=_auth(student),
        json={"session_token": first_body["session_token"]},
    )
    second = await client.post(
        f"/api/v1/assessments/{assessment_id}/start",
        headers=_auth(student),
        json={"application_id": application_id},
    )
    assert second.status_code == 201

    participation = await client.get(
        f"/api/v1/assessments/placement/{drive_id}/participation?assessment_id={assessment_id}",
        headers=_auth(admin),
    )
    assert participation.status_code == 200
    summary = participation.json()
    assert summary["eligible_students"] == 1
    assert summary["attempts_started"] == 2
    assert summary["submitted"] == 1
    assert summary["in_progress"] == 1
