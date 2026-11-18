"""Focused tests for the role-specific dashboard analytics endpoints.

Covers the student domain radar + score trend, the TPO application analytics
(department / month / company aggregation, date filters, Top-N) and the admin
activity endpoint, plus the role boundaries on each new route.
"""
from datetime import datetime, timedelta

import pytest
from bson import ObjectId

from app.core import database as db_module
from app.models.assessment import PLACEMENT_SECTIONS
from app.models.user import AdminRegisterRequest
from app.services.auth_service import AuthService

FUTURE_DEADLINE = (datetime.utcnow() + timedelta(days=30)).isoformat()
MINIMAL_PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


# ---------------------------------------------------------------------------
# Helpers (mirroring tests/test_analytics.py)
# ---------------------------------------------------------------------------
async def _register_login_student(client, email, *, department="CS"):
    await client.post(
        "/api/v1/auth/register/student",
        json={
            "email": email,
            "password": "StrongPass123",
            "name": "Dashboard Student",
            "department": department,
            "batch_year": 2026,
        },
    )
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


async def _register_login_tpo(client, email):
    await client.post(
        "/api/v1/auth/register/tpo",
        json={"email": email, "password": "StrongPass123", "name": "Dashboard TPO", "department_scope": []},
    )
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


async def _register_login_admin(client, email):
    service = AuthService(db_module.mongodb.db)
    await service.register_admin(AdminRegisterRequest(email=email, password="StrongPass123", name="Dashboard Admin"))
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _drive_payload(**overrides):
    payload = {
        "company_name": "Dashboard Corp",
        "job_title": "Software Engineer",
        "description": "Build things",
        "jd_text": "We need a software engineer.",
        "required_skills": ["Python"],
        "eligibility": {},
        "deadline": FUTURE_DEADLINE,
        "selection_process": [],
    }
    payload.update(overrides)
    return payload


async def _student_doc(email: str) -> dict:
    db = db_module.mongodb.db
    user = await db.users.find_one({"email": email})
    return await db.students.find_one({"user_id": str(user["_id"])})


async def _apply(client, token: str, drive_id: str) -> str:
    await client.post(
        "/api/v1/resumes",
        headers=_auth_headers(token),
        files={"file": ("resume.pdf", MINIMAL_PDF_BYTES, "application/pdf")},
    )
    response = await client.post(f"/api/v1/drives/{drive_id}/apply", headers=_auth_headers(token))
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


async def _set_status(client, tpo_token: str, drive_id: str, application_id: str, status: str):
    response = await client.patch(
        f"/api/v1/drives/{drive_id}/applications/{application_id}",
        headers=_auth_headers(tpo_token),
        json={"status": status},
    )
    assert response.status_code == 200, response.text


async def _insert_standardized_attempt(student: dict) -> str:
    """Insert a real standardized assessment + one graded submitted attempt.

    One question per canonical section, all medium. The student answers the
    Quantitative, Verbal and Programming questions correctly and the Logical
    and Technical questions incorrectly, giving a 3/5 domain spread and a
    60% overall score.
    """
    db = db_module.mongodb.db
    creator = ObjectId()
    section_ids: dict[str, list[str]] = {}
    answers = []

    for index, section in enumerate(PLACEMENT_SECTIONS):
        question_id = ObjectId()
        await db.questions.insert_one(
            {
                "_id": question_id,
                "category_id": str(ObjectId()),
                "skill_tags": [section],
                "difficulty": "medium",
                "type": "mcq",
                "text": f"{section} question",
                "options": ["A", "B"],
                "correct_answer": "A",
                "marks": 3,
                "created_by": str(creator),
                "created_at": datetime.utcnow(),
            }
        )
        section_ids[section] = [str(question_id)]
        is_correct = section in {"Quantitative Aptitude", "Verbal Ability", "Programming / Problem Solving"}
        answers.append(
            {
                "question_id": str(question_id),
                "response": "A" if is_correct else "B",
                "is_correct": is_correct,
                "marks_awarded": 3 if is_correct else 0,
                "difficulty_at_time": "medium",
                "question_type": "mcq",
            }
        )

    assessment_id = ObjectId()
    await db.assessments.insert_one(
        {
            "_id": assessment_id,
            "title": "Standardized Dashboard Assessment",
            "category_ids": [],
            "type": "practice",
            "created_by": str(creator),
            "created_at": datetime.utcnow(),
            "format": "standardized",
            "status": "published",
            "question_ids": [qid for ids in section_ids.values() for qid in ids],
            "sections": [
                {"name": section, "question_ids": section_ids[section], "count": 1}
                for section in PLACEMENT_SECTIONS
            ],
            "total_marks": 15,
        }
    )

    submitted_at = datetime.utcnow() - timedelta(days=1)
    await db.assessment_attempts.insert_one(
        {
            "assessment_id": str(assessment_id),
            "student_id": str(student["_id"]),
            "session_token": "dashboard-session",
            "asked_question_ids": [a["question_id"] for a in answers],
            "answers": answers,
            "status": "submitted",
            "started_at": submitted_at - timedelta(minutes=20),
            "submitted_at": submitted_at,
        }
    )
    return str(assessment_id)


# ---------------------------------------------------------------------------
# Student analytics
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_student_analytics_status_counts_domain_radar_and_trend(client):
    tpo_token = await _register_login_tpo(client, "dash.tpo@college.edu")
    student_email = "dash.student@college.edu"
    student_token = await _register_login_student(client, student_email)

    shortlist_drive = await client.post("/api/v1/drives", headers=_auth_headers(tpo_token), json=_drive_payload())
    reject_drive = await client.post(
        "/api/v1/drives",
        headers=_auth_headers(tpo_token),
        json=_drive_payload(company_name="Reject Corp", job_title="Analyst"),
    )
    shortlist_drive_id = shortlist_drive.json()["id"]
    reject_drive_id = reject_drive.json()["id"]

    shortlisted_app = await _apply(client, student_token, shortlist_drive_id)
    rejected_app = await _apply(client, student_token, reject_drive_id)
    await _set_status(client, tpo_token, shortlist_drive_id, shortlisted_app, "shortlisted")
    await _set_status(client, tpo_token, reject_drive_id, rejected_app, "rejected")

    student = await _student_doc(student_email)
    assert student is not None
    await _insert_standardized_attempt(student)

    # Two attempts that must NOT be treated as completed assessments: one
    # still in progress and one submitted with no answers at all.
    db = db_module.mongodb.db
    await db.assessment_attempts.insert_one(
        {
            "assessment_id": str(ObjectId()),
            "student_id": str(student["_id"]),
            "session_token": "in-progress-session",
            "answers": [],
            "status": "in_progress",
            "started_at": datetime.utcnow(),
        }
    )
    await db.assessment_attempts.insert_one(
        {
            "assessment_id": str(ObjectId()),
            "student_id": str(student["_id"]),
            "session_token": "empty-submitted-session",
            "answers": [],
            "status": "submitted",
            "started_at": datetime.utcnow() - timedelta(days=2),
            "submitted_at": datetime.utcnow() - timedelta(days=2),
        }
    )

    response = await client.get("/api/v1/analytics/student/me", headers=_auth_headers(student_token))
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["applications"] == {"applied": 0, "shortlisted": 1, "rejected": 1, "selected": 0}
    assert data["total_applications"] == 2
    # Rates use this student's own applications as the denominator.
    assert data["applied_rate_pct"] == 0.0
    assert data["shortlisting_rate_pct"] == 50.0
    assert data["rejection_rate_pct"] == 50.0

    domains = {row["domain"]: row for row in data["domain_scores"]}
    assert list(domains) == list(PLACEMENT_SECTIONS)
    assert domains["Quantitative Aptitude"]["score_pct"] == 100.0
    assert domains["Logical Reasoning"]["score_pct"] == 0.0
    assert domains["Verbal Ability"]["score_pct"] == 100.0
    assert domains["Technical Knowledge"]["score_pct"] == 0.0
    assert domains["Programming / Problem Solving"]["score_pct"] == 100.0
    for row in domains.values():
        assert row["answered"] == 1
    assert domains["Logical Reasoning"]["correct"] == 0

    # Only the one genuinely graded attempt contributes; the in-progress and
    # empty submitted attempts are excluded from both the trend and the count.
    assert data["submitted_attempt_count"] == 1
    assert len(data["assessment_trend"]) == 1
    point = data["assessment_trend"][0]
    assert point["assessment_title"] == "Standardized Dashboard Assessment"
    assert point["score_pct"] == 60.0
    assert point["correct"] == 3
    assert point["answered"] == 5


@pytest.mark.asyncio
async def test_student_analytics_empty_state_is_real_zeros(client):
    student_token = await _register_login_student(client, "dash.empty.student@college.edu")
    response = await client.get("/api/v1/analytics/student/me", headers=_auth_headers(student_token))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_applications"] == 0
    assert data["submitted_attempt_count"] == 0
    # A zero denominator yields 0.0, never a division error or a fake rate.
    assert data["applied_rate_pct"] == 0.0
    assert data["shortlisting_rate_pct"] == 0.0
    assert data["rejection_rate_pct"] == 0.0
    assert data["assessment_trend"] == []
    assert [row["domain"] for row in data["domain_scores"]] == list(PLACEMENT_SECTIONS)
    assert all(row["score_pct"] == 0.0 and row["answered"] == 0 for row in data["domain_scores"])


# ---------------------------------------------------------------------------
# TPO application analytics
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tpo_application_analytics_departments_companies_and_date_filters(client):
    tpo_token = await _register_login_tpo(client, "dash.apps.tpo@college.edu")
    alpha = await client.post(
        "/api/v1/drives", headers=_auth_headers(tpo_token), json=_drive_payload(company_name="Alpha Corp")
    )
    beta = await client.post(
        "/api/v1/drives",
        headers=_auth_headers(tpo_token),
        json=_drive_payload(company_name="Beta Corp", job_title="Data Analyst"),
    )
    alpha_id = alpha.json()["id"]
    beta_id = beta.json()["id"]

    cs_token = await _register_login_student(client, "dash.cs@college.edu", department="CS")
    it_token = await _register_login_student(client, "dash.it@college.edu", department="IT")
    both_token = await _register_login_student(client, "dash.both@college.edu", department="CS")

    cs_app = await _apply(client, cs_token, alpha_id)
    it_app = await _apply(client, it_token, beta_id)
    await _apply(client, both_token, alpha_id)
    await _apply(client, both_token, beta_id)

    await _set_status(client, tpo_token, alpha_id, cs_app, "shortlisted")
    await _set_status(client, tpo_token, beta_id, it_app, "rejected")

    # Move every application into January 2026 so the date filters are exact
    # and the zero-filled February/March buckets are exercised.
    db = db_module.mongodb.db
    await db.applications.update_many({}, {"$set": {"applied_at": datetime(2026, 1, 15, 12, 0, 0)}})

    response = await client.get(
        "/api/v1/analytics/tpo/applications?date_from=2026-01-01&date_to=2026-03-31",
        headers=_auth_headers(tpo_token),
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["total_applications"] == 4
    assert data["total_drives"] == 2
    assert data["status_breakdown"] == {"applied": 2, "shortlisted": 1, "rejected": 1}
    # Three students produced four applications: unique applicants must not
    # be the application-row count.
    assert data["unique_applicants"] == 3
    assert data["applied_rate_pct"] == 50.0
    assert data["shortlisting_rate_pct"] == 25.0
    assert data["rejection_rate_pct"] == 25.0

    # Per-drive comparison only lists drives that actually received an
    # application, with their real status split.
    drives = {row["company_name"]: row for row in data["drives"]}
    assert set(drives) == {"Alpha Corp", "Beta Corp"}
    assert data["drive_count"] == 2
    assert drives["Alpha Corp"]["total"] == 2
    assert drives["Alpha Corp"]["shortlisted"] == 1
    assert drives["Beta Corp"]["total"] == 2
    assert drives["Beta Corp"]["rejected"] == 1

    departments = {row["department"]: row for row in data["departments"]}
    assert departments["Computer Science"]["applied"] == 2
    assert departments["Computer Science"]["shortlisted"] == 1
    assert departments["Computer Science"]["total"] == 3
    assert departments["Information Technology"]["rejected"] == 1
    assert departments["Information Technology"]["total"] == 1

    months = {row["month"]: row for row in data["monthly_trend"]}
    assert list(months) == ["2026-01", "2026-02", "2026-03"]
    assert months["2026-01"]["total"] == 4
    assert months["2026-01"]["applied"] == 2
    assert months["2026-01"]["shortlisted"] == 1
    assert months["2026-01"]["rejected"] == 1
    assert months["2026-02"]["total"] == 0
    assert months["2026-03"]["total"] == 0

    companies = {row["company_name"]: row for row in data["companies"]}
    assert companies["Alpha Corp"]["total"] == 2
    assert companies["Alpha Corp"]["shortlisted"] == 1
    assert companies["Beta Corp"]["total"] == 2
    assert companies["Beta Corp"]["rejected"] == 1
    assert data["company_count"] == 2

    # Out-of-range window: a real zero, not a fallback to the full history.
    empty = await client.get(
        "/api/v1/analytics/tpo/applications?date_from=2026-02-01&date_to=2026-02-28",
        headers=_auth_headers(tpo_token),
    )
    assert empty.status_code == 200, empty.text
    empty_data = empty.json()
    assert empty_data["total_applications"] == 0
    assert empty_data["status_breakdown"] == {"applied": 0, "shortlisted": 0, "rejected": 0}
    assert empty_data["unique_applicants"] == 0
    assert empty_data["shortlisting_rate_pct"] == 0.0
    assert empty_data["drives"] == []
    assert empty_data["drive_count"] == 0
    assert empty_data["departments"] == []
    assert [row["month"] for row in empty_data["monthly_trend"]] == ["2026-02"]
    assert empty_data["monthly_trend"][0]["total"] == 0

    # Top-N truncation keeps the true company count.
    top_one = await client.get(
        "/api/v1/analytics/tpo/applications?date_from=2026-01-01&date_to=2026-03-31&top_n=1&company_sort=name",
        headers=_auth_headers(tpo_token),
    )
    assert top_one.status_code == 200, top_one.text
    top_one_data = top_one.json()
    assert len(top_one_data["companies"]) == 1
    assert top_one_data["companies"][0]["company_name"] == "Alpha Corp"
    assert top_one_data["company_count"] == 2

    invalid = await client.get(
        "/api/v1/analytics/tpo/applications?date_from=2026-03-01&date_to=2026-01-01",
        headers=_auth_headers(tpo_token),
    )
    assert invalid.status_code == 400


@pytest.mark.asyncio
async def test_tpo_application_analytics_is_scoped_to_own_drives(client):
    owner_token = await _register_login_tpo(client, "dash.scope.owner@college.edu")
    other_token = await _register_login_tpo(client, "dash.scope.other@college.edu")
    owner_drive = await client.post(
        "/api/v1/drives", headers=_auth_headers(owner_token), json=_drive_payload(company_name="Owner Corp")
    )
    other_drive = await client.post(
        "/api/v1/drives", headers=_auth_headers(other_token), json=_drive_payload(company_name="Other Corp")
    )

    student_token = await _register_login_student(client, "dash.scope.student@college.edu")
    await _apply(client, student_token, owner_drive.json()["id"])
    await _apply(client, student_token, other_drive.json()["id"])

    response = await client.get("/api/v1/analytics/tpo/applications", headers=_auth_headers(owner_token))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_drives"] == 1
    assert data["total_applications"] == 1
    assert [row["company_name"] for row in data["companies"]] == ["Owner Corp"]


@pytest.mark.asyncio
async def test_tpo_application_records_drilldown_filters_and_pagination(client):
    """The drill-down behind every chart returns the exact matching rows."""
    tpo_token = await _register_login_tpo(client, "dash.records.tpo@college.edu")
    alpha = await client.post(
        "/api/v1/drives", headers=_auth_headers(tpo_token), json=_drive_payload(company_name="Alpha Corp")
    )
    beta = await client.post(
        "/api/v1/drives",
        headers=_auth_headers(tpo_token),
        json=_drive_payload(company_name="Beta Corp", job_title="Data Analyst"),
    )
    alpha_id = alpha.json()["id"]
    beta_id = beta.json()["id"]

    cs_token = await _register_login_student(client, "dash.records.cs@college.edu", department="CS")
    it_token = await _register_login_student(client, "dash.records.it@college.edu", department="IT")
    both_token = await _register_login_student(client, "dash.records.both@college.edu", department="CS")

    cs_app = await _apply(client, cs_token, alpha_id)
    it_app = await _apply(client, it_token, beta_id)
    await _apply(client, both_token, alpha_id)
    await _apply(client, both_token, beta_id)

    await _set_status(client, tpo_token, alpha_id, cs_app, "shortlisted")
    await _set_status(client, tpo_token, beta_id, it_app, "rejected")

    analytics = await client.get("/api/v1/analytics/tpo/applications", headers=_auth_headers(tpo_token))
    assert analytics.status_code == 200, analytics.text
    alpha_company_id = next(
        row["company_id"] for row in analytics.json()["companies"] if row["company_name"] == "Alpha Corp"
    )

    all_rows = await client.get(
        "/api/v1/analytics/tpo/applications/records", headers=_auth_headers(tpo_token)
    )
    assert all_rows.status_code == 200, all_rows.text
    all_data = all_rows.json()
    assert all_data["total"] == 4
    assert len(all_data["entries"]) == 4
    assert {entry["status"] for entry in all_data["entries"]} == {"applied", "shortlisted", "rejected"}
    # Drill-down exposes identity + outcome only, never contact details.
    # `is_synthetic` is the provenance flag the UI uses to mark demo rows.
    entry = all_data["entries"][0]
    assert set(entry) == {
        "application_id",
        "student_id",
        "student_name",
        "department",
        "drive_id",
        "job_title",
        "company_id",
        "company_name",
        "status",
        "applied_at",
        "is_synthetic",
    }
    assert entry["is_synthetic"] is False

    by_status = await client.get(
        "/api/v1/analytics/tpo/applications/records?status=shortlisted",
        headers=_auth_headers(tpo_token),
    )
    assert by_status.status_code == 200, by_status.text
    status_data = by_status.json()
    assert status_data["total"] == 1
    assert status_data["entries"][0]["company_name"] == "Alpha Corp"
    assert status_data["entries"][0]["status"] == "shortlisted"

    by_department = await client.get(
        "/api/v1/analytics/tpo/applications/records?department=Computer%20Science",
        headers=_auth_headers(tpo_token),
    )
    assert by_department.status_code == 200, by_department.text
    assert by_department.json()["total"] == 3

    by_company = await client.get(
        f"/api/v1/analytics/tpo/applications/records?company_id={alpha_company_id}",
        headers=_auth_headers(tpo_token),
    )
    assert by_company.status_code == 200, by_company.text
    assert by_company.json()["total"] == 2

    by_drive = await client.get(
        f"/api/v1/analytics/tpo/applications/records?drive_id={alpha_id}",
        headers=_auth_headers(tpo_token),
    )
    assert by_drive.status_code == 200, by_drive.text
    assert by_drive.json()["total"] == 2

    page_one = await client.get(
        "/api/v1/analytics/tpo/applications/records?page=1&limit=2",
        headers=_auth_headers(tpo_token),
    )
    page_two = await client.get(
        "/api/v1/analytics/tpo/applications/records?page=2&limit=2",
        headers=_auth_headers(tpo_token),
    )
    assert page_one.json()["total"] == page_two.json()["total"] == 4
    assert len(page_one.json()["entries"]) == 2
    assert len(page_two.json()["entries"]) == 2
    assert {
        entry["application_id"] for entry in page_one.json()["entries"]
    }.isdisjoint({entry["application_id"] for entry in page_two.json()["entries"]})

    unknown_drive = await client.get(
        f"/api/v1/analytics/tpo/applications/records?drive_id={ObjectId()}",
        headers=_auth_headers(tpo_token),
    )
    assert unknown_drive.status_code == 404

    # Another TPO cannot see these rows, and a student cannot call the route.
    other_token = await _register_login_tpo(client, "dash.records.other@college.edu")
    other_rows = await client.get(
        "/api/v1/analytics/tpo/applications/records", headers=_auth_headers(other_token)
    )
    assert other_rows.status_code == 200
    assert other_rows.json()["total"] == 0
    assert (
        await client.get(
            "/api/v1/analytics/tpo/applications/records", headers=_auth_headers(cs_token)
        )
    ).status_code == 403


# ---------------------------------------------------------------------------
# Admin activity
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_activity_user_distribution_departments_and_monthly_series(client):
    await _register_login_admin(client, "dash.admin@college.edu")
    tpo_token = await _register_login_tpo(client, "dash.activity.tpo@college.edu")
    await _register_login_student(client, "dash.activity.cs@college.edu", department="CS")
    student_token = await _register_login_student(
        client, "dash.activity.ee@college.edu", department="Electrical Engineering"
    )

    drive = await client.post("/api/v1/drives", headers=_auth_headers(tpo_token), json=_drive_payload())
    await _apply(client, student_token, drive.json()["id"])

    admin_token = await _register_login_admin(client, "dash.activity.admin@college.edu")
    response = await client.get("/api/v1/analytics/admin/activity", headers=_auth_headers(admin_token))
    assert response.status_code == 200, response.text
    data = response.json()

    roles = {row["role"]: row["count"] for row in data["user_distribution"]}
    assert roles == {"student": 2, "tpo": 1, "admin": 2}
    assert data["total_users"] == 5

    departments = {row["department"]: row["count"] for row in data["department_student_counts"]}
    assert departments == {"Computer Science": 1, "Electrical Engineering": 1}

    # Every account/drive/application was created this month, so the single
    # current bucket must match the real totals. "New students" counts only
    # student accounts, not TPO/admin signups.
    assert len(data["monthly_activity"]) == 1
    current = data["monthly_activity"][0]
    assert current["new_students"] == 2
    assert current["new_drives"] == 1
    assert current["applications"] == 1

    # The existing admin analytics payload is extended additively.
    admin = await client.get("/api/v1/analytics/admin", headers=_auth_headers(admin_token))
    assert admin.status_code == 200, admin.text
    admin_data = admin.json()
    assert admin_data["total_admins"] == 2
    # One student applied, so one unique applicant backs one application.
    assert admin_data["unique_applicants"] == 1
    assert {row["role"]: row["count"] for row in admin_data["user_role_counts"]} == roles
    assert {
        row["department"]: row["count"] for row in admin_data["department_student_counts"]
    } == departments


# ---------------------------------------------------------------------------
# Data-quality fallbacks
# ---------------------------------------------------------------------------
def test_department_normalization_merges_aliases_and_preserves_unknown_text():
    from app.services.analytics_service import _normalize_department

    assert _normalize_department("  cs ") == "Computer Science"
    assert _normalize_department("Computer Science & Engineering") == "Computer Science"
    assert _normalize_department("IT") == "Information Technology"
    assert _normalize_department("B.Tech CSE (AI)") == "B.Tech CSE (AI)"
    assert _normalize_department("") == "Not specified"
    assert _normalize_department(None) == "Not specified"


@pytest.mark.asyncio
async def test_admin_activity_uses_objectid_time_when_created_at_is_missing(client):
    """A legacy account with no stored created_at keeps its real month.

    The ObjectId embeds the insert time, so this is the document's own
    creation date - not a guess and not "now".
    """
    admin_token = await _register_login_admin(client, "dash.legacy.admin@college.edu")
    db = db_module.mongodb.db
    legacy_id = ObjectId.from_datetime(datetime(2026, 1, 15, 9, 0, 0))
    await db.users.insert_one(
        {
            "_id": legacy_id,
            "email": "legacy.student@college.edu",
            "password_hash": None,
            "role": "student",
            "auth_provider": "local",
            "is_active": True,
            # deliberately no created_at
        }
    )

    response = await client.get("/api/v1/analytics/admin/activity", headers=_auth_headers(admin_token))
    assert response.status_code == 200, response.text
    data = response.json()

    months = {row["month"]: row for row in data["monthly_activity"]}
    assert months["2026-01"]["new_students"] == 1
    assert data["total_users"] == 2
    assert {row["role"]: row["count"] for row in data["user_distribution"]}["student"] == 1


# ---------------------------------------------------------------------------
# Role boundaries
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dashboard_analytics_role_boundaries(client):
    student_token = await _register_login_student(client, "dash.rbac.student@college.edu")
    tpo_token = await _register_login_tpo(client, "dash.rbac.tpo@college.edu")
    admin_token = await _register_login_admin(client, "dash.rbac.admin@college.edu")

    assert (
        await client.get("/api/v1/analytics/tpo/applications", headers=_auth_headers(student_token))
    ).status_code == 403
    assert (
        await client.get("/api/v1/analytics/admin/activity", headers=_auth_headers(student_token))
    ).status_code == 403
    assert (
        await client.get("/api/v1/analytics/admin/activity", headers=_auth_headers(tpo_token))
    ).status_code == 403
    assert (
        await client.get("/api/v1/analytics/student/me", headers=_auth_headers(tpo_token))
    ).status_code == 403
    assert (
        await client.get("/api/v1/analytics/student/me", headers=_auth_headers(admin_token))
    ).status_code == 403

    assert (
        await client.get("/api/v1/analytics/student/me", headers=_auth_headers(student_token))
    ).status_code == 200
    assert (
        await client.get("/api/v1/analytics/tpo/applications", headers=_auth_headers(tpo_token))
    ).status_code == 200
    assert (
        await client.get("/api/v1/analytics/admin/activity", headers=_auth_headers(admin_token))
    ).status_code == 200
