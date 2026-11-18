"""Import genuinely public job postings into the market dataset.

Usage (from ``backend/``, with the project venv)::

    .venv\\Scripts\\python.exe -m scripts.import_job_market --source remoteok
    .venv\\Scripts\\python.exe -m scripts.import_job_market --source arbeitnow --dry-run
    .venv\\Scripts\\python.exe -m scripts.import_job_market --all
    .venv\\Scripts\\python.exe -m scripts.import_job_market --list-sources

Only documented public APIs are used. Every imported row keeps its source id,
source URL, licence string and import timestamp; mock demo rows are never
modified. Each run writes a ``market_import_runs`` audit document, including
dry runs.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import get_settings
from app.core.database import ensure_market_indexes
from app.repositories.job_posting_repository import JobMarketPostingRepository
from app.services.market_import_service import ADAPTERS, MarketImportService
from app.services.market_sources import MARKET_SOURCES


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
    db = client[settings.MONGODB_DB_NAME]

    try:
        await client.admin.command("ping")
        await ensure_market_indexes(db)

        if args.list_sources:
            repo = JobMarketPostingRepository(db)
            stats = {row["_id"]: row for row in await repo.source_stats()}
            for source_id, definition in sorted(MARKET_SOURCES.items()):
                stat = stats.get(source_id, {})
                print(
                    f"{source_id:12} {definition.label:38} "
                    f"postings={stat.get('posting_count', 0):5} "
                    f"latest_import={stat.get('imported_at')}"
                )
            return 0

        sources = list(ADAPTERS) if args.all else [args.source]
        service = MarketImportService(db)
        exit_code = 0
        for source in sources:
            print(f"Importing {source} ...")
            result = await service.import_source(
                source, dry_run=args.dry_run, limit=args.limit
            )
            prefix = "DRY RUN" if result.dry_run else "IMPORT"
            print(
                f"  {prefix} {result.source}: status={result.status} "
                f"fetched={result.fetched} imported={result.imported} "
                f"duplicates={result.duplicates} skipped={result.skipped} "
                f"version={result.dataset_version}"
            )
            for error in result.errors[:10]:
                print(f"    error: {error}")
            if result.errors and len(result.errors) > 10:
                print(f"    ... {len(result.errors) - 10} more error(s)")
            if result.status == "failed":
                exit_code = 1
        return exit_code
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import public job postings into the market dataset."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--source",
        choices=sorted(ADAPTERS),
        help="Import one public source.",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Import every supported public source.",
    )
    group.add_argument(
        "--list-sources",
        action="store_true",
        help="Show known sources and their stored posting counts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch, normalise and validate without writing postings.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N fetched postings (testing).",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    started = datetime.utcnow()
    code = asyncio.run(_run(args))
    print(f"Finished in {(datetime.utcnow() - started).total_seconds():.1f}s")
    sys.exit(code)


if __name__ == "__main__":
    main()
