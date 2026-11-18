"""Regression tests for analytics that must be traceable to real data.

Covers the accuracy fixes made after the analytics audit:
  * assessment is part of matching/ranking scores;
  * admin aggregates are exact even when list fetches are capped;
  * student insight trends use submitted attempts only;
  * market trend scores never mix a partial latest year with full years.
"""
from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from bson import ObjectId

import app.services.analytics_service as analytics_module
from app.models.assessment import AttemptStatus
from app.services.analytics_service import AnalyticsService
from app.services.market_analytics_service import _trend_score
from app.services.matching_service import MatchCandidate, MatchingService, compute_final_score
from app.services.student_insights_service import StudentInsightsService


# ---------------------------------------------------------------------------
# Matching / ranking
# ---------------------------------------------------------------------------


def test_compute_final_score_includes_assessment_component():
    no_assessment = compute_final_score(1.0, 1.0, 1.0)
    half_assessment = compute_final_score(
        1.0, 1.0, 1.0, assessment_score_pct=50.0, has_assessment=True
    )
    assert no_assessment == pytest.approx(1.0)
    # 0.40 + 0.30 + 0.20 + 0.10 * 0.50
    assert half_assessment == pytest.approx(0.95)


def test_ranked_resume_scores_include_each_applicants_assessment(monkeypatch):
    service = MatchingService(None)
    monkeypatch.setattr(service, "_cross_score_pairs", lambda _pairs: np.array([0.5, 0.5]))

    jd = MatchCandidate("jd", "jd", {"python"}, 2.0, None)
    strong = MatchCandidate("r-strong", "a", {"python"}, 2.0, None)
    weak = MatchCandidate("r-weak", "b", {"python"}, 2.0, None)

    results = service._score_one_jd_vs_many_resumes(
        jd,
        [strong, weak],
        assessment_scores_by_id={"r-strong": 80.0},
        has_assessment=True,
    )
    by_id = {row["candidate_id"]: row for row in results}

    # Both have identical semantic/skills/experience; the 80% assessment is
    # the only difference. No score on file gives full credit (canonical rule).
    # 0.4*0.5 + 0.3*1 + 0.2*1 + 0.1*0.8 = 0.78; without it = 0.80.
    assert by_id["r-strong"]["final_score"] == pytest.approx(0.78)
    assert by_id["r-weak"]["final_score"] == pytest.approx(0.80)
    assert by_id["r-strong"]["final_score"] < by_id["r-weak"]["final_score"]


# ---------------------------------------------------------------------------
# Admin analytics exact aggregates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_analytics_stays_exact_when_fetch_limit_is_lowered(mock_mongo, monkeypatch):
    monkeypatch.setattr(analytics_module, "_ANALYTICS_FETCH_LIMIT", 2)
    db = mock_mongo

    for index in range(5):
        await db.applications.insert_one(
            {
                "status": "selected" if index < 3 else "applied",
                "student_id": f"student-{index % 2}",
            }
        )
    for index in range(4):
        await db.assessment_attempts.insert_one(
            {
                "status": "submitted" if index < 2 else "in_progress",
                "answers": [
                    {
                        "marks_awarded": 1 if index == 0 else 0,
                        "difficulty_at_time": "easy",
                    }
                ],
            }
        )
    await db.knowledge_states.insert_many(
        [
            {"skill_tag": "Python", "mastery_pct": 80.0},
            {"skill_tag": "Python", "mastery_pct": 60.0},
            {"skill_tag": "SQL", "mastery_pct": 90.0},
        ]
    )

    result = await AnalyticsService(db).get_admin_analytics()

    assert result.total_applications == 5
    # Legacy selected rows are mapped into shortlisted for the current
    # three-status view; no Selected stage is reported.
    assert result.application_breakdown.selected == 0
    assert result.application_breakdown.applied == 2
    assert result.application_breakdown.shortlisted == 3
    assert result.legacy_selected == 3
    # 3 selected applications belong to only 2 distinct students.
    assert result.placed_students == 2
    assert result.total_attempts == 4
    assert result.submitted_attempts == 2
    # attempt 0 = 100%, attempt 1 = 0% -> average 50%
    assert result.average_score_pct == pytest.approx(50.0)
    overview = {row.skill_tag: row for row in result.skill_mastery_overview}
    assert overview["Python"].avg_mastery_pct == pytest.approx(70.0)
    assert overview["Python"].student_count == 2


@pytest.mark.asyncio
async def test_admin_average_score_is_none_without_scoreable_attempts(mock_mongo):
    """No scored attempts must not be reported as an average of 0%."""
    result = await AnalyticsService(mock_mongo).get_admin_analytics()
    assert result.submitted_attempts == 0
    assert result.average_score_pct is None


# ---------------------------------------------------------------------------
# Student insights
# ---------------------------------------------------------------------------


def test_insight_trend_uses_only_submitted_attempt_accuracy():
    now = datetime(2026, 1, 1)
    points = [
        (now, 40.0),
        (now + timedelta(days=1), 60.0),
        (now + timedelta(days=2), 80.0),
    ]
    assert StudentInsightsService._trend_from_attempts(points) == "improving"
    declining = [
        (points[0][0], 80.0),
        (points[1][0], 60.0),
        (points[2][0], 40.0),
    ]
    assert StudentInsightsService._trend_from_attempts(declining) == "declining"
    # A fluctuation is not a trend (points are sorted by timestamp first).
    fluctuating = [
        (points[0][0], 40.0),
        (points[1][0], 80.0),
        (points[2][0], 60.0),
    ]
    assert StudentInsightsService._trend_from_attempts(fluctuating) == "steady"
    assert StudentInsightsService._trend_from_attempts(points[:1]) == "unknown"
    assert StudentInsightsService._trend_from_attempts([]) == "unknown"


@pytest.mark.asyncio
async def test_insight_build_ignores_in_progress_attempts_and_deleted_questions(mock_mongo):
    service = StudentInsightsService(mock_mongo)
    question_id = str(ObjectId())
    question = SimpleNamespace(
        id=question_id,
        text="2 + 2 = ?",
        skill_tags=["Arithmetic"],
        difficulty="easy",
        type="mcq",
        correct_answer="4",
    )

    def make_attempt(status, score, offset):
        return SimpleNamespace(
            id=str(ObjectId()),
            status=status,
            answers=[
                SimpleNamespace(
                    question_id=question_id,
                    is_correct=score,
                    response="4",
                    difficulty_at_time="easy",
                    marks_awarded=1 if score else 0,
                ),
                # This question no longer exists in the bank.
                SimpleNamespace(
                    question_id=str(ObjectId()),
                    is_correct=False,
                    response="old",
                    difficulty_at_time="easy",
                    marks_awarded=0,
                ),
            ],
            started_at=datetime(2026, 1, 1) + timedelta(days=offset),
            submitted_at=datetime(2026, 1, 1) + timedelta(days=offset),
        )

    submitted_wrong = make_attempt(AttemptStatus.SUBMITTED, False, 0)
    submitted_right = make_attempt(AttemptStatus.SUBMITTED, True, 1)
    in_progress = make_attempt(AttemptStatus.IN_PROGRESS, True, 2)

    async def fake_resolve(_user_id):
        return "student-profile"

    async def fake_attempts(_student_id):
        return [submitted_wrong, submitted_right, in_progress]

    async def fake_count(_query):
        return 3

    async def fake_states(_student_id):
        return []

    async def fake_questions(_query, limit=None):
        return [question]

    async def fake_narrate(_result):
        return None

    service._resolve_student_id = fake_resolve
    service.attempts.get_for_student = fake_attempts
    service.attempts.count_for_student = fake_count
    service.knowledge_states.get_all_for_student = fake_states
    service.questions.find_many = fake_questions
    service._maybe_narrate = fake_narrate

    result = await service.build("user-1")

    assert result.total_attempts == 2
    # Two submitted answers, one correct; the deleted question contributes
    # nothing and the in-progress correct answer is excluded.
    assert result.total_questions_answered == 2
    assert result.overall_accuracy_pct == pytest.approx(50.0)
    assert result.total_questions_answered < 3 * 2


# ---------------------------------------------------------------------------
# Market trend windows
# ---------------------------------------------------------------------------


def test_trend_score_uses_comparable_when_latest_year_is_partial():
    years = [2023, 2024, 2025, 2026]
    full_skill = Counter({year: count for year, count in zip(years, [10, 10, 10, 6])})
    full_totals = Counter({year: 100 for year in years})
    # Same data-driven window in every year: a 60-posting subset each year.
    partial_skill = Counter({year: 6 for year in years})
    partial_totals = Counter({year: 60 for year in years})

    mixed = _trend_score(full_skill, full_totals, years, latest_year=2026)
    comparable = _trend_score(
        full_skill,
        full_totals,
        years,
        latest_year=2026,
        skill_yearly_window=partial_skill,
        yearly_totals_window=partial_totals,
        use_partial_window=True,
    )
    assert mixed < comparable
    assert comparable == pytest.approx(10.0)
