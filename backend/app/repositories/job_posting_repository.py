"""Repositories for the historical job-market dataset."""
from typing import Any

from app.models.market import JobMarketPostingInDB, MarketSkillCatalogInDB
from app.repositories.base import BaseRepository


class JobMarketPostingRepository(BaseRepository[JobMarketPostingInDB]):
    collection_name = "job_market_postings"
    model = JobMarketPostingInDB

    async def create_many(self, documents: list[dict[str, Any]]) -> int:
        """Validate then bulk-insert postings.

        Validation is intentionally done before the insert so a generator bug
        cannot put a malformed document into the analytics collection. The
        original dictionaries are inserted rather than model dumps: the seed
        config already uses JSON/BSON-friendly primitive values, and this
        avoids accidentally persisting enum objects.
        """
        if not documents:
            return 0
        for document in documents:
            self.model.model_validate(document)
        result = await self.collection.insert_many(documents)
        return len(result.inserted_ids)

    async def find_projected(
        self,
        query: dict[str, Any] | None = None,
        projection: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read raw projected documents without Pydantic model validation.

        Used by the market analytics service, which needs aggregate-level
        fields only (never job descriptions or JD text) and should not pay
        full-model validation cost for every posting on every request.
        """
        cursor = self.collection.find(query or {}, projection or {})
        if limit is not None:
            cursor = cursor.limit(limit)
        return [document async for document in cursor]

    async def distinct_values(
        self, field: str, query: dict[str, Any] | None = None
    ) -> list[Any]:
        """Distinct values of a field, optionally scoped by a query."""
        return await self.collection.distinct(field, query or {})

    async def existing_external_ids(self, external_ids: list[str]) -> set[str]:
        """Subset of ``external_ids`` already present (import dedupe)."""
        if not external_ids:
            return set()
        cursor = self.collection.find(
            {"external_id": {"$in": external_ids}}, {"_id": 0, "external_id": 1}
        )
        return {row["external_id"] async for row in cursor}

    async def month_coverage(
        self, query: dict[str, Any] | None = None
    ) -> dict[int, int]:
        """Highest month present per year in the (source-scoped) dataset.

        The analytics comparison window is derived from actual data coverage,
        not a hardcoded "Jan-Oct" constant, so postings dated in November or
        December are never silently dropped. Coverage is computed over the
        whole source population (never the user's year/company filter), so a
        narrow filter cannot shrink the window and distort YoY comparisons.
        """
        pipeline: list[dict[str, Any]] = [
            {"$match": query or {}},
            {"$group": {"_id": "$year", "max_month": {"$max": "$month"}}},
        ]
        coverage: dict[int, int] = {}
        async for row in self.collection.aggregate(pipeline):
            year = row.get("_id")
            month = row.get("max_month")
            if isinstance(year, int) and isinstance(month, int):
                coverage[year] = max(1, min(12, month))
        return coverage

    async def source_stats(self) -> list[dict[str, Any]]:
        """Per-source counts plus the newest posting/import timestamps."""
        pipeline: list[dict[str, Any]] = [
            {
                "$group": {
                    "_id": "$source",
                    "posting_count": {"$sum": 1},
                    "latest_posted_at": {"$max": "$posted_at"},
                    "imported_at": {"$max": "$imported_at"},
                }
            },
            {"$sort": {"posting_count": -1, "_id": 1}},
        ]
        return [row async for row in self.collection.aggregate(pipeline)]

    async def company_counts(
        self, query: dict[str, Any] | None = None, limit: int | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Posting counts per company, highest first, plus the distinct total.

        Used to build filter options without reading every posting document:
        the option list is capped, but ``total`` always reports the true number
        of distinct companies so the UI never claims the list is complete.
        """
        return await self._value_counts("company_slug", "company_name", query, limit)

    async def location_counts(
        self, query: dict[str, Any] | None = None, limit: int | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Posting counts per location, highest first, plus the distinct total."""
        return await self._value_counts("location", "location", query, limit)

    async def _value_counts(
        self,
        field: str,
        name_field: str,
        query: dict[str, Any] | None,
        limit: int | None,
    ) -> tuple[list[dict[str, Any]], int]:
        pipeline: list[dict[str, Any]] = [
            {"$match": query or {}},
            {
                "$group": {
                    "_id": f"${field}",
                    "name": {"$first": f"${name_field}"},
                    "posting_count": {"$sum": 1},
                }
            },
            {"$sort": {"posting_count": -1, "name": 1}},
        ]
        if limit is not None:
            pipeline.append({"$limit": limit})
        rows = [row async for row in self.collection.aggregate(pipeline)]
        total = len(await self.distinct_values(field, query))
        return rows, total


class MarketSkillCatalogRepository(BaseRepository[MarketSkillCatalogInDB]):
    collection_name = "market_skill_catalog"
    model = MarketSkillCatalogInDB

    async def create_many(self, documents: list[dict[str, Any]]) -> int:
        if not documents:
            return 0
        for document in documents:
            self.model.model_validate(document)
        result = await self.collection.insert_many(documents)
        return len(result.inserted_ids)
