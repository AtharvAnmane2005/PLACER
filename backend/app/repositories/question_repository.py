import re

from bson import ObjectId

from app.models.assessment import QuestionCategoryInDB, QuestionInDB
from app.repositories.base import BaseRepository


class QuestionCategoryRepository(BaseRepository[QuestionCategoryInDB]):
    collection_name = "question_categories"
    model = QuestionCategoryInDB


class QuestionRepository(BaseRepository[QuestionInDB]):
    collection_name = "questions"
    model = QuestionInDB

    async def find_by_filters(
        self,
        category_id: str | None = None,
        difficulty: str | None = None,
        skill_tag: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[QuestionInDB]:
        query: dict = {}
        if category_id:
            query["category_id"] = category_id
        if difficulty:
            query["difficulty"] = difficulty
        if skill_tag:
            query["skill_tags"] = skill_tag
        return await self.find_many(query, page=page, limit=limit)

    async def search(
        self,
        *,
        search: str | None = None,
        category_id: str | None = None,
        difficulty: str | None = None,
        question_type: str | None = None,
        topic: str | None = None,
        skill: str | None = None,
        status: str | None = None,
        ids: list[str] | None = None,
        limit: int = 200,
    ) -> list[QuestionInDB]:
        """Admin question-bank search. All filters are ANDed; text search
        covers question text, topic, skill and company/skill tags.
        Legacy documents without ``status`` are treated as active.
        """
        query: dict = {}
        if search:
            pattern = re.escape(search.strip())
            query["$or"] = [
                {"text": {"$regex": pattern, "$options": "i"}},
                {"topic": {"$regex": pattern, "$options": "i"}},
                {"skill_tags": {"$regex": pattern, "$options": "i"}},
                {"company_tags": {"$regex": pattern, "$options": "i"}},
            ]
        if category_id:
            query["category_id"] = category_id
        if difficulty:
            query["difficulty"] = difficulty
        if question_type:
            query["type"] = question_type
        if topic:
            query["topic"] = {"$regex": f"^{re.escape(topic)}$", "$options": "i"}
        if skill:
            skill_pattern = f"^{re.escape(skill)}$"
            query["$and"] = query.get("$and", []) + [
                {"$or": [{"skill": {"$regex": skill_pattern, "$options": "i"}}, {"skill_tags": {"$regex": skill_pattern, "$options": "i"}}]}
            ]
        if status == "active":
            query["status"] = {"$in": ["active", None]}
        elif status == "inactive":
            query["status"] = "inactive"
        if ids is not None:
            valid = [ObjectId(i) for i in ids if ObjectId.is_valid(i)]
            query["_id"] = {"$in": valid}
        return await self.find_many(query, limit=limit)

    async def stats(self) -> dict:
        """Count questions by category, difficulty and type using one pass."""
        docs = await self.find_many({}, limit=100000)
        by_category: dict[str, int] = {}
        by_difficulty: dict[str, int] = {}
        by_type: dict[str, int] = {}
        active = 0
        for q in docs:
            by_category[q.category_id] = by_category.get(q.category_id, 0) + 1
            by_difficulty[q.difficulty.value] = by_difficulty.get(q.difficulty.value, 0) + 1
            by_type[q.type.value] = by_type.get(q.type.value, 0) + 1
            if q.status.value == "active":
                active += 1
        return {
            "total": len(docs),
            "active": active,
            "inactive": len(docs) - active,
            "by_category": by_category,
            "by_difficulty": by_difficulty,
            "by_type": by_type,
        }

    async def find_by_ids(self, ids: list[str]) -> list[QuestionInDB]:
        """Return questions in the exact order of ``ids`` (missing IDs skipped)."""
        if not ids:
            return []
        docs = await self.find_many({"_id": {"$in": [ObjectId(i) for i in ids if ObjectId.is_valid(i)]}}, limit=len(ids))
        by_id = {q.id: q for q in docs}
        return [by_id[i] for i in ids if i in by_id]

    async def bulk_insert(self, documents: list[dict]) -> list[QuestionInDB]:
        """Insert a fully pre-validated batch in one ordered bulk operation."""
        if not documents:
            return []
        result = await self.collection.insert_many(documents, ordered=True)
        return [await self.get_by_id(str(inserted_id)) for inserted_id in result.inserted_ids]

    async def find_duplicate(self, text: str, exclude_id: str | None = None) -> QuestionInDB | None:
        normalized = " ".join(text.strip().lower().split())
        query = {"text": {"$regex": f"^{re.escape(normalized)}$", "$options": "i"}}
        if exclude_id and ObjectId.is_valid(exclude_id):
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        return await self.find_one(query)

    async def get_random_unused(
        self, category_ids: list[str], difficulty: str, exclude_ids: list[str]
    ) -> QuestionInDB | None:
        """
        Picks one question at the target difficulty from the given
        categories, excluding ones already asked in this attempt. Uses a
        simple "fetch candidates, pick randomly in Python" approach rather
        than Mongo's $sample — the question pools here are small enough
        (tens to low hundreds per category/difficulty) that this is both
        simpler and avoids $sample's known small-collection bias, and it
        works identically against mongomock in tests.
        """
        import random

        query: dict = {"difficulty": difficulty}
        if category_ids:
            query["category_id"] = {"$in": category_ids}
        if exclude_ids:
            valid_exclude = [eid for eid in exclude_ids if ObjectId.is_valid(eid)]
            query["_id"] = {"$nin": [ObjectId(eid) for eid in valid_exclude]}
        # Inactive questions must never be selected for a new attempt.
        query["status"] = {"$in": ["active", None]}

        candidates = await self.find_many(query, page=1, limit=200)
        return random.choice(candidates) if candidates else None
