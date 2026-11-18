from app.models.drive import ApplicationInDB
from app.repositories.base import BaseRepository


class ApplicationRepository(BaseRepository[ApplicationInDB]):
    collection_name = "applications"
    model = ApplicationInDB

    async def get_existing(self, drive_id: str, student_id: str) -> ApplicationInDB | None:
        return await self.find_one({"drive_id": drive_id, "student_id": student_id})

    async def get_for_student(self, student_id: str, page: int = 1, limit: int = 20) -> list[ApplicationInDB]:
        return await self.find_many({"student_id": student_id}, page=page, limit=limit, sort=[("applied_at", -1)])

    async def get_for_drive(self, drive_id: str, page: int = 1, limit: int = 50) -> list[ApplicationInDB]:
        return await self.find_many({"drive_id": drive_id}, page=page, limit=limit, sort=[("applied_at", -1)])

    async def status_counts(self) -> dict[str, int]:
        """Exact status counts from the collection, not a capped document fetch.

        Admin analytics must never mix a true `count()` total with a status
        breakdown computed from only the first N rows — that silently reports
        some numbers as totals and others as lower bounds.
        """
        cursor = self.collection.aggregate(
            [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        )
        return {
            doc["_id"]: doc["count"]
            async for doc in cursor
            if isinstance(doc.get("_id"), str)
        }

    async def distinct_students_by_status(self, status: str) -> list[str]:
        """Unique student ids with an application in the given status."""
        return await self.collection.distinct("student_id", {"status": status})

    async def distinct_students(self) -> list[str]:
        """Unique student ids across every application status.

        This is the correct denominator for "how many students actually
        applied", as opposed to the application-row total. A student who
        applied to three drives is still one applicant.
        """
        return await self.collection.distinct("student_id", {})
