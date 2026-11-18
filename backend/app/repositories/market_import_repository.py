"""Repository for the job-market import audit log."""
from app.models.market_import import MarketImportRunInDB
from app.repositories.base import BaseRepository


class MarketImportRunRepository(BaseRepository[MarketImportRunInDB]):
    collection_name = "market_import_runs"
    model = MarketImportRunInDB

    async def latest(self, source: str | None = None) -> MarketImportRunInDB | None:
        query = {"source": source} if source else {}
        rows = await self.find_many(query, limit=1, sort=[("started_at", -1)])
        return rows[0] if rows else None
