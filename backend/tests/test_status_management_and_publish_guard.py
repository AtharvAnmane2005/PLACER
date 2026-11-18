"""Status management, audit trail and the drive-publish assessment guard.

These cover the workflow rules that are easy to regress:

* Admins may manage applications on any drive; TPOs only on their own.
* ``selected`` is never settable through the API.
* Every status change writes an audit entry with before/after state.
* A drive cannot be (re)opened or have its assessment cleared while open
  without an assessment attached.
"""
from datetime import datetime, timedelta

import pytest

from app.core import database as db_module
from app.models.user import AdminRegisterRequest
from app.services.auth_service import AuthService

FUTURE_DEADLINE = (datetime.utcnow() + timedelta(days=30)).isoformat()
MINIMAL_PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
ASSESSMENT_REQUIRED_MESSAGE = (
    "An assessment is required before this placement drive can be published."
)


async def _register_login_tpo(client, email="guard.tpo@college.edu"):
    await client.post(
        "/api/v1/auth/register/tpo",
        json={"email": email, "password": "StrongPass123", "name": "Guard TPO", "department_scope": []},
    )
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


async def _register_login_admin(client, email="guard.admin@college.edu"):
    service = AuthService(db_module.mongodb.db)
    await service.register_admin(
        AdminRegisterRequest(email=email, password="StrongPass123", name="Guard Admin")
    )
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


async def _register_login_student(client, email="guard.student@college.edu"):
    await client.post(
        "/api/v1/auth/register/student",
        json={
            "email": email,
            "password": "StrongPass123",
            "name": "Guard Student",
            "department": "CS",
            "batch_year": 2026,
        },
    )
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    return login.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _drive_payload(**overrides):
    payload = {
        "company_name": "Guard Corp",
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


async def _create_drive_with_application(client, tpo_token):
    drive = await client.post("/api/v1/drives", headers=_auth(tpo_token), json=_drive_payload())
    assert drive.status_code == 201, drive.text
    drive_id = drive.json()["id"]

    student_token = await _register_login_student(client)
    upload = await client.post(
        "/api/v1/resumes",
        headers=_auth(student_token),
        files={"file": ("resume.pdf", MINIMAL_PDF_BYTES, "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    application = await client.post(f"/api/v1/drives/{drive_id}/apply", headers=_auth(student_token))
    assert application.status_code == 201, application.text
    return drive_id, application.json()["id"]


@pytest.mark.asyncio
async def test_admin_can_manage_status_on_a_tpo_drive_and_audit_is_written(client):
    tpo_token = await _register_login_tpo(client)
    admin_token = await _register_login_admin(client)
    drive_id, application_id = await _create_drive_with_application(client, tpo_token)

    response = await client.patch(
        f"/api/v1/drives/{drive_id}/applications/{application_id}",
        headers=_auth(admin_token),
        json={"status": "shortlisted"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "shortlisted"

    logs = await db_module.mongodb.db.activity_logs.find(
        {"entity": "application", "entity_id": application_id}
    ).to_list(length=None)
    assert len(logs) == 1
    log = logs[0]
    assert log["action"] == "application.status_changed"
    metadata = log["metadata"]
    assert metadata["drive_id"] == drive_id
    assert metadata["previous_status"] == "applied"
    assert metadata["new_status"] == "shortlisted"
    assert metadata["actor_role"] == "admin"
    # The audit row must record when the change happened, not just what.
    assert log.get("timestamp") is not None


@pytest.mark.asyncio
async def test_selected_is_rejected_but_managed_statuses_can_toggle(client):
    tpo_token = await _register_login_tpo(client, "toggle.tpo@college.edu")
    drive_id, application_id = await _create_drive_with_application(client, tpo_token)

    selected = await client.patch(
        f"/api/v1/drives/{drive_id}/applications/{application_id}",
        headers=_auth(tpo_token),
        json={"status": "selected"},
    )
    assert selected.status_code == 400
    detail = selected.json()["detail"].lower()
    assert "applied" in detail and "shortlisted" in detail and "rejected" in detail

    # A decision can be reversed; the workflow is not a one-way terminal graph.
    for status in ("rejected", "shortlisted", "applied", "shortlisted"):
        response = await client.patch(
            f"/api/v1/drives/{drive_id}/applications/{application_id}",
            headers=_auth(tpo_token),
            json={"status": status},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status


@pytest.mark.asyncio
async def test_admin_can_list_applications_on_a_tpo_drive(client):
    """The admin applications page reads a TPO-owned drive's applicants.

    Admins already may change status on any drive; without read access the
    UI could not show the rows they are changing.
    """
    tpo_token = await _register_login_tpo(client, "list.tpo@college.edu")
    admin_token = await _register_login_admin(client, "list.admin@college.edu")
    drive_id, application_id = await _create_drive_with_application(client, tpo_token)

    response = await client.get(
        f"/api/v1/drives/{drive_id}/applications", headers=_auth(admin_token)
    )
    assert response.status_code == 200, response.text
    entries = response.json()
    assert [entry["id"] for entry in entries] == [application_id]
    assert entries[0]["is_synthetic"] is False


@pytest.mark.asyncio
async def test_tpo_cannot_list_another_tpos_applications(client):
    owner_token = await _register_login_tpo(client, "owner.tpo@college.edu")
    other_token = await _register_login_tpo(client, "other.tpo@college.edu")
    drive_id, _ = await _create_drive_with_application(client, owner_token)

    response = await client.get(
        f"/api/v1/drives/{drive_id}/applications", headers=_auth(other_token)
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_reopening_a_drive_without_an_assessment_is_rejected(client):
    tpo_token = await _register_login_tpo(client, "reopen.tpo@college.edu")
    drive = await client.post("/api/v1/drives", headers=_auth(tpo_token), json=_drive_payload())
    drive_id = drive.json()["id"]
    assert drive.json()["required_assessment_id"] is None

    closed = await client.put(
        f"/api/v1/drives/{drive_id}", headers=_auth(tpo_token), json={"status": "closed"}
    )
    assert closed.status_code == 200, closed.text

    reopen = await client.put(
        f"/api/v1/drives/{drive_id}", headers=_auth(tpo_token), json={"status": "open"}
    )
    assert reopen.status_code == 400, reopen.text
    assert reopen.json()["detail"] == ASSESSMENT_REQUIRED_MESSAGE

    # Still closed: the failed reopen must not have partially applied.
    detail = await client.get(f"/api/v1/drives/{drive_id}", headers=_auth(tpo_token))
    assert detail.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_clearing_the_assessment_on_an_open_drive_is_rejected(client):
    tpo_token = await _register_login_tpo(client, "clear.tpo@college.edu")
    drive = await client.post("/api/v1/drives", headers=_auth(tpo_token), json=_drive_payload())
    drive_id = drive.json()["id"]

    # An empty string is the API's way to clear the linkage (null is treated
    # as "not supplied" by the partial-update semantics).
    response = await client.put(
        f"/api/v1/drives/{drive_id}",
        headers=_auth(tpo_token),
        json={"required_assessment_id": ""},
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == ASSESSMENT_REQUIRED_MESSAGE
