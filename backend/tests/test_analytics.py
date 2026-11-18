from datetime import datetime, timedelta

import pytest

from app.core import database as db_module
from app.models.drive import VALID_STATUS_TRANSITIONS, ApplicationStatus
from app.models.user import AdminRegisterRequest
from app.services.auth_service import AuthService

FUTURE_DEADLINE = (datetime.utcnow() + timedelta(days=30)).isoformat()
MINIMAL_PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.mark.asyncio
async def test_selected_status_is_not_settable_and_managed_statuses_toggle(client):
    """The TPO workflow exposes only Applied / Shortlisted / Rejected.

    A request to set ``selected`` is rejected, and the three managed statuses
    can be freely toggled because a placement team may reverse a decision.
    """
    tpo_token = await _register_login_tpo(client, "transitions.tpo@college.edu")
    drive = await client.post("/api/v1/drives", headers=_auth_headers(tpo_token), json=_drive_payload())
    drive_id = drive.json()["id"]

    application_id = await _apply_with_new_student(client, drive_id, "transitions.applicant@college.edu")

    selected = await client.patch(
        f"/api/v1/drives/{drive_id}/applications/{application_id}",
        headers=_auth_headers(tpo_token),
        json={"status": "selected"},
    )
    assert selected.status_code == 400
    detail = selected.json()["detail"].lower()
    assert "applied" in detail and "shortlisted" in detail and "rejected" in detail

    for status in ("rejected", "shortlisted", "applied", "rejected"):
        response = await client.patch(
            f"/api/v1/drives/{drive_id}/applications/{application_id}",
            headers=_auth_headers(tpo_token),
            json={"status": status},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status

    # The declared table agrees with the enforced workflow: Selected is never
    # a managed target, and the managed statuses point at each other.
    assert ApplicationStatus.SELECTED not in VALID_STATUS_TRANSITIONS[ApplicationStatus.APPLIED]
    assert ApplicationStatus.SELECTED not in VALID_STATUS_TRANSITIONS[ApplicationStatus.SHORTLISTED]
    assert VALID_STATUS_TRANSITIONS[ApplicationStatus.APPLIED] == {
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.REJECTED,
    }
    assert VALID_STATUS_TRANSITIONS[ApplicationStatus.SHORTLISTED] == {
        ApplicationStatus.APPLIED,
        ApplicationStatus.REJECTED,
    }
    assert VALID_STATUS_TRANSITIONS[ApplicationStatus.REJECTED] == {
        ApplicationStatus.APPLIED,
        ApplicationStatus.SHORTLISTED,
    }
    # A legacy Selected record can be corrected back into the workflow.
    assert ApplicationStatus.REJECTED in VALID_STATUS_TRANSITIONS[ApplicationStatus.SELECTED]


async def _register_login_student(client, email):
    await client.post(
        "/api/v1/auth/register/student",
        json={
            "email": email,
            "password": "StrongPass123",
            "name": "Analytics Student",
            "department": "CS",
            "batch_year": 2026,
        },
    )
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


async def _register_login_tpo(client, email):
    await client.post(
        "/api/v1/auth/register/tpo",
        json={"email": email, "password": "StrongPass123", "name": "Analytics TPO", "department_scope": []},
    )
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


async def _register_login_admin(client, email):
    from app.core import database as db_module

    service = AuthService(db_module.mongodb.db)
    await service.register_admin(AdminRegisterRequest(email=email, password="StrongPass123", name="Analytics Admin"))
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _drive_payload(**overrides):
    payload = {
        "company_name": "Analytics Corp",
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


async def _apply_with_new_student(client, drive_id: str, email: str) -> str:
    student_token = await _register_login_student(client, email)
    await client.post(
        "/api/v1/resumes",
        headers=_auth_headers(student_token),
        files={"file": ("resume.pdf", MINIMAL_PDF_BYTES, "application/pdf")},
    )
    apply_response = await client.post(f"/api/v1/drives/{drive_id}/apply", headers=_auth_headers(student_token))
    return apply_response.json()["id"]


@pytest.mark.asyncio
async def test_tpo_analytics_reflects_own_drives_only(client):
    owner_token = await _register_login_tpo(client, "analytics.owner@college.edu")
    other_token = await _register_login_tpo(client, "analytics.other@college.edu")

    owned_drive = await client.post("/api/v1/drives", headers=_auth_headers(owner_token), json=_drive_payload())
    owned_drive_id = owned_drive.json()["id"]
    await client.post("/api/v1/drives", headers=_auth_headers(other_token), json=_drive_payload())

    application_id = await _apply_with_new_student(client, owned_drive_id, "analytics.applicant1@college.edu")
    await client.patch(
        f"/api/v1/drives/{owned_drive_id}/applications/{application_id}",
        headers=_auth_headers(owner_token),
        json={"status": "shortlisted"},
    )
    await _apply_with_new_student(client, owned_drive_id, "analytics.applicant2@college.edu")

    response = await client.get("/api/v1/analytics/tpo", headers=_auth_headers(owner_token))
    assert response.status_code == 200
    data = response.json()

    assert data["total_drives"] == 1  # only the owner's drive, not the other TPO's
    assert data["total_applications"] == 2
    assert data["breakdown"]["shortlisted"] == 1
    assert data["breakdown"]["applied"] == 1
    # The TPO pipeline has no Selected stage: the key is absent, not zero.
    assert "selected" not in data["breakdown"]
    assert "selection_rate_pct" not in data
    assert len(data["drives"]) == 1
    assert data["drives"][0]["total_applications"] == 2


@pytest.mark.asyncio
async def test_admin_applications_workspace_filters_and_status_mapping(client):
    admin_token = await _register_login_admin(client, "workspace.admin@college.edu")
    tpo_token = await _register_login_tpo(client, "workspace.tpo@college.edu")
    drive = await client.post(
        "/api/v1/drives", headers=_auth_headers(tpo_token), json=_drive_payload()
    )
    drive_id = drive.json()["id"]
    first_id = await _apply_with_new_student(client, drive_id, "workspace.one@college.edu")
    second_id = await _apply_with_new_student(client, drive_id, "workspace.two@college.edu")

    # Admin status changes use the existing audited endpoint.
    shortlisted = await client.patch(
        f"/api/v1/drives/{drive_id}/applications/{first_id}",
        headers=_auth_headers(admin_token),
        json={"status": "shortlisted"},
    )
    assert shortlisted.status_code == 200, shortlisted.text

    response = await client.get(
        "/api/v1/analytics/admin/applications", headers=_auth_headers(admin_token)
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 2
    assert data["summary"]["total"] == 2
    assert data["summary"]["applied"] == 1
    assert data["summary"]["shortlisted"] == 1
    row = next(entry for entry in data["entries"] if entry["application_id"] == first_id)
    assert row["student_name"]
    assert row["company_name"] == "Analytics Corp"
    assert row["job_title"] == "Software Engineer"
    assert row["status"] == "shortlisted"

    by_status = await client.get(
        "/api/v1/analytics/admin/applications?status=shortlisted",
        headers=_auth_headers(admin_token),
    )
    assert by_status.json()["total"] == 1

    by_department = await client.get(
        "/api/v1/analytics/admin/applications?department=CS",
        headers=_auth_headers(admin_token),
    )
    assert by_department.json()["total"] == 2

    # A legacy selected row is exposed as shortlisted, never as a fourth stage.
    from bson import ObjectId

    await db_module.mongodb.db.applications.update_one(
        {"_id": ObjectId(second_id)}, {"$set": {"status": "selected"}}
    )
    mapped = await client.get(
        "/api/v1/analytics/admin/applications?status=shortlisted",
        headers=_auth_headers(admin_token),
    )
    assert mapped.json()["total"] == 2
    assert all(entry["status"] == "shortlisted" for entry in mapped.json()["entries"])

    filters = await client.get(
        "/api/v1/analytics/admin/applications/filters", headers=_auth_headers(admin_token)
    )
    assert filters.status_code == 200, filters.text
    filter_data = filters.json()
    assert any(company["name"] == "Analytics Corp" for company in filter_data["companies"])
    assert any(item["id"] == drive_id for item in filter_data["drives"])
    assert "Computer Science" in filter_data["departments"]


@pytest.mark.asyncio
async def test_student_and_tpo_cannot_access_admin_analytics(client):
    student_token = await _register_login_student(client, "noanalytics.student@college.edu")
    tpo_token = await _register_login_tpo(client, "noanalytics.tpo@college.edu")

    student_response = await client.get("/api/v1/analytics/admin", headers=_auth_headers(student_token))
    tpo_response = await client.get("/api/v1/analytics/admin", headers=_auth_headers(tpo_token))
    assert student_response.status_code == 403
    assert tpo_response.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_access_tpo_analytics(client):
    student_token = await _register_login_student(client, "noanalytics2.student@college.edu")
    response = await client.get("/api/v1/analytics/tpo", headers=_auth_headers(student_token))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_analytics_counts_placements_and_applications(client):
    admin_token = await _register_login_admin(client, "counts.admin@college.edu")
    tpo_token = await _register_login_tpo(client, "counts.tpo@college.edu")

    drive = await client.post("/api/v1/drives", headers=_auth_headers(tpo_token), json=_drive_payload())
    drive_id = drive.json()["id"]

    application_id = await _apply_with_new_student(client, drive_id, "counts.applicant@college.edu")

    # The live API no longer produces Selected; a legacy selected record is
    # written directly to prove the admin placement metric still counts real
    # stored outcomes (and to keep the legacy path covered).
    from bson import ObjectId

    await db_module.mongodb.db.applications.update_one(
        {"_id": ObjectId(application_id)},
        {"$set": {"status": "selected"}},
    )

    response = await client.get("/api/v1/analytics/admin", headers=_auth_headers(admin_token))
    assert response.status_code == 200
    data = response.json()

    assert data["total_drives"] >= 1
    assert data["total_applications"] >= 1
    # The current analytics have no Selected stage: the legacy row is mapped
    # into Shortlisted at read time, and the audit count records the mapping.
    assert data["application_breakdown"]["selected"] == 0
    assert data["application_breakdown"]["shortlisted"] >= 1
    assert data["legacy_selected"] >= 1
    # The internal legacy placement count is still derived from real records.
    assert data["placed_students"] >= 1
