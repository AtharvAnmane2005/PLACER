from app.models.assessment import KnowledgeStateInDB
from app.repositories.base import BaseRepository


class KnowledgeStateRepository(BaseRepository[KnowledgeStateInDB]):
    collection_name = "knowledge_states"
    model = KnowledgeStateInDB

    async def get_by_student_and_skill(self, student_id: str, skill_tag: str) -> KnowledgeStateInDB | None:
        return await self.find_one({"student_id": student_id, "skill_tag": skill_tag})

    async def get_all_for_student(self, student_id: str) -> list[KnowledgeStateInDB]:
        return await self.find_many({"student_id": student_id}, sort=[("mastery_pct", -1)], limit=200)

    async def mastery_overview(self) -> list[dict]:
        """Exact average mastery and student count per skill tag.

        Computed in the database so the admin dashboard never presents a
        5,000-row sample as if it were the whole collection.
        """
        cursor = self.collection.aggregate(
            [
                {
                    "$group": {
                        "_id": "$skill_tag",
                        "average": {"$avg": "$mastery_pct"},
                        "student_count": {"$sum": 1},
                    }
                }
            ]
        )
        return [
            {
                "skill_tag": doc["_id"],
                "avg_mastery_pct": doc["average"],
                "student_count": doc["student_count"],
            }
            async for doc in cursor
            if isinstance(doc.get("_id"), str)
        ]
