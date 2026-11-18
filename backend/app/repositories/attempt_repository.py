from app.models.assessment import AssessmentAttemptInDB
from app.repositories.base import BaseRepository


class AttemptRepository(BaseRepository[AssessmentAttemptInDB]):
    collection_name = "assessment_attempts"
    model = AssessmentAttemptInDB

    # Cap on a student's full attempt history. High enough that no realistic
    # student reaches it, but present so a pathological account can't pull an
    # unbounded set into memory. Callers that aggregate over this should treat
    # hitting the cap as "history is incomplete" and say so rather than
    # silently reporting partial totals.
    HISTORY_FETCH_LIMIT = 500

    async def get_for_student(self, student_id: str) -> list[AssessmentAttemptInDB]:
        """Every attempt for a student, newest first.

        Deliberately NOT paginated. This feeds cross-attempt aggregation
        (knowledge tracing, student insights), where silently dropping older
        attempts would bias the student's accuracy and trend figures with no
        visible symptom.
        """
        return await self.find_many(
            {"student_id": student_id},
            sort=[("started_at", -1)],
            limit=self.HISTORY_FETCH_LIMIT,
        )

    async def count_for_student(self, student_id: str) -> int:
        """Total attempt count, so callers can detect that get_for_student()
        returned a capped (i.e. incomplete) history."""
        return await self.count({"student_id": student_id})

    async def submitted_score_stats(self, easy_marks: int, medium_marks: int, hard_marks: int) -> tuple[int, float | None]:
        """Exact (submitted_count, average_score_pct) computed in the database.

        The score uses the same difficulty-at-time weights as the service-level
        scorer, so the average cannot drift when a fetch cap is hit. Returns
        the raw average (callers round for display) or None when no submitted
        attempt has a nonzero maximum score.
        """
        submitted_count = await self.count({"status": "submitted"})
        pipeline = [
            {"$match": {"status": "submitted"}},
            {"$unwind": "$answers"},
            {
                "$group": {
                    "_id": "$_id",
                    "total": {"$sum": "$answers.marks_awarded"},
                    "maximum": {
                        "$sum": {
                            "$switch": {
                                "branches": [
                                    {"case": {"$eq": ["$answers.difficulty_at_time", "easy"]}, "then": easy_marks},
                                    {"case": {"$eq": ["$answers.difficulty_at_time", "medium"]}, "then": medium_marks},
                                    {"case": {"$eq": ["$answers.difficulty_at_time", "hard"]}, "then": hard_marks},
                                ],
                                "default": 0,
                            }
                        }
                    },
                }
            },
            {"$match": {"maximum": {"$gt": 0}}},
            {
                "$group": {
                    "_id": None,
                    "average": {
                        "$avg": {"$multiply": [100, {"$divide": ["$total", "$maximum"]}]}
                    },
                    "scored_attempts": {"$sum": 1},
                }
            },
        ]
        rows = [doc async for doc in self.collection.aggregate(pipeline)]
        average = rows[0]["average"] if rows else None
        return submitted_count, average
