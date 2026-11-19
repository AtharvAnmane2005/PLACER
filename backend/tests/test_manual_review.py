"""Adaptive mark bounds and manual grading of descriptive answers."""
import pytest


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register_login_admin(client, email):
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
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "StrongPass123"}
    )
    return login.json()["access_token"]


async def _register_login_student(client, email):
    await client.post(
        "/api/v1/auth/register/student",
        json={
            "email": email,
            "password": "StrongPass123",
            "name": "Review Student",
            "department": "CS",
            "batch_year": 2026,
        },
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "StrongPass123"}
    )
    return login.json()["access_token"]


async def _register_login_tpo(client, email):
    await client.post(
        "/api/v1/auth/register/tpo",
        json={
            "email": email,
            "password": "StrongPass123",
            "name": "Review TPO",
            "department_scope": [],
        },
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "StrongPass123"}
    )
    return login.json()["access_token"]


async def _create_category(client, admin_token, name):
    response = await client.post(
        "/api/v1/questions/categories", headers=_auth_headers(admin_token), json={"name": name}
    )
    return response.json()["id"]


async def _create_descriptive_question(client, admin_token, category_id):
    response = await client.post(
        "/api/v1/questions",
        headers=_auth_headers(admin_token),
        json={
            "category_id": category_id,
            "skill_tags": ["Communication"],
            "difficulty": "medium",
            "type": "descriptive",
            "text": "Explain how you would design a rate limiter.",
            "correct_answer": None,
            "explanation": "Look for token bucket, limits, and failure modes.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_adaptive_assessment_stores_top_n_total_marks(client):
    admin_token = await _register_login_admin(client, "marks.admin@college.edu")
    category_id = await _create_category(client, admin_token, "MarksCat")

    # Two hard (5) + one easy (1): a 2-question pool can earn at most 10.
    for index, (difficulty, correct) in enumerate((("hard", "A"), ("hard", "B"), ("easy", "C"))):
        created = await client.post(
            "/api/v1/questions",
            headers=_auth_headers(admin_token),
            json={
                "category_id": category_id,
                "skill_tags": ["Algorithms"],
                "difficulty": difficulty,
                "type": "mcq",
                "text": f"{difficulty} question {index}?",
                "options": ["A", "B", "C", "D"],
                "correct_answer": correct,
            },
        )
        assert created.status_code == 201, created.text

    response = await client.post(
        "/api/v1/assessments",
        headers=_auth_headers(admin_token),
        json={
            "title": "Marks Bound",
            "category_ids": [category_id],
            "question_pool_size": 2,
            "time_limit_sec": 1800,
            "max_violations": 3,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["total_marks"] == 10

    listed = await client.get("/api/v1/assessments", headers=_auth_headers(admin_token))
    row = next(item for item in listed.json() if item["id"] == response.json()["id"])
    assert row["total_marks"] == 10


@pytest.mark.asyncio
async def test_descriptive_answer_can_be_graded_by_tpo(client):
    admin_token = await _register_login_admin(client, "review.admin@college.edu")
    category_id = await _create_category(client, admin_token, "ReviewCat")
    question = await _create_descriptive_question(client, admin_token, category_id)

    assessment = await client.post(
        "/api/v1/assessments",
        headers=_auth_headers(admin_token),
        json={
            "title": "Descriptive Practice",
            "category_ids": [category_id],
            "question_pool_size": 1,
            "time_limit_sec": 1800,
            "max_violations": 3,
        },
    )
    assessment_id = assessment.json()["id"]

    student_token = await _register_login_student(client, "review.student@college.edu")
    start = await client.post(
        f"/api/v1/assessments/{assessment_id}/start",
        headers=_auth_headers(student_token),
        json={},
    )
    assert start.status_code == 201, start.text
    attempt = start.json()
    assert attempt["next_question"]["type"] == "descriptive"

    answer = await client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/answer",
        headers=_auth_headers(student_token),
        json={
            "session_token": attempt["session_token"],
            "question_id": question["id"],
            "response": "Use a token bucket with a per-key limit and a shared store.",
        },
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["is_correct"] is None
    assert answer.json()["attempt_status"] == "submitted"

    # Before grading the student sees a pending-review answer with no marks.
    results = await client.get(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/results",
        headers=_auth_headers(student_token),
    )
    assert results.status_code == 200
    detail = results.json()["answers"][0]
    assert detail["is_correct"] is None
    assert detail["graded_at"] is None
    assert detail["feedback"] is None

    # Students cannot use the review API.
    forbidden = await client.get(
        "/api/v1/assessments/review/pending", headers=_auth_headers(student_token)
    )
    assert forbidden.status_code == 403

    tpo_token = await _register_login_tpo(client, "review.tpo@college.edu")
    pending = await client.get(
        "/api/v1/assessments/review/pending", headers=_auth_headers(tpo_token)
    )
    assert pending.status_code == 200, pending.text
    item = next(row for row in pending.json() if row["attempt_id"] == attempt["attempt_id"])
    assert item["pending_count"] == 1
    assert item["student_name"] == "Review Student"

    review = await client.get(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/review",
        headers=_auth_headers(tpo_token),
    )
    assert review.status_code == 200, review.text
    assert review.json()["answers"][0]["question_text"] == question["text"]

    # Marks are clamped to the question's maximum.
    graded = await client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/grade",
        headers=_auth_headers(tpo_token),
        json={
            "question_id": question["id"],
            "marks_awarded": 99,
            "feedback": "Good structure; add failure-mode handling.",
        },
    )
    assert graded.status_code == 200, graded.text
    body = graded.json()
    assert body["marks_awarded"] == question["marks"]
    assert body["is_correct"] is True
    assert body["pending_count"] == 0

    # The pending queue is now empty for this TPO.
    pending_after = await client.get(
        "/api/v1/assessments/review/pending", headers=_auth_headers(tpo_token)
    )
    assert all(
        row["attempt_id"] != attempt["attempt_id"] for row in pending_after.json()
    )

    # The student sees the grade and reviewer feedback.
    results_after = await client.get(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/results",
        headers=_auth_headers(student_token),
    )
    detail_after = results_after.json()["answers"][0]
    assert detail_after["graded_at"] is not None
    assert detail_after["feedback"] == "Good structure; add failure-mode handling."
    assert detail_after["marks_awarded"] == question["marks"]
    assert results_after.json()["total_marks"] == question["marks"]


@pytest.mark.asyncio
async def test_only_descriptive_answers_can_be_manually_graded(client):
    admin_token = await _register_login_admin(client, "onlydesc.admin@college.edu")
    category_id = await _create_category(client, admin_token, "OnlyDescCat")
    mcq = await client.post(
        "/api/v1/questions",
        headers=_auth_headers(admin_token),
        json={
            "category_id": category_id,
            "skill_tags": ["Python"],
            "difficulty": "medium",
            "type": "mcq",
            "text": "Pick A",
            "options": ["A", "B"],
            "correct_answer": "A",
        },
    )
    mcq = mcq.json()

    assessment = await client.post(
        "/api/v1/assessments",
        headers=_auth_headers(admin_token),
        json={
            "title": "Objective Practice",
            "category_ids": [category_id],
            "question_pool_size": 1,
            "time_limit_sec": 1800,
            "max_violations": 3,
        },
    )
    student_token = await _register_login_student(client, "onlydesc.student@college.edu")
    start = await client.post(
        f"/api/v1/assessments/{assessment.json()['id']}/start",
        headers=_auth_headers(student_token),
        json={},
    )
    attempt = start.json()
    await client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/answer",
        headers=_auth_headers(student_token),
        json={
            "session_token": attempt["session_token"],
            "question_id": mcq["id"],
            "response": "A",
        },
    )

    response = await client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/grade",
        headers=_auth_headers(admin_token),
        json={"question_id": mcq["id"], "marks_awarded": 1},
    )
    assert response.status_code == 400
    assert "descriptive" in response.json()["detail"].lower()
