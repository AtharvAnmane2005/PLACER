"""Drop and recreate the *local* PLACER database.

Safety rules, in order:

1. The connection string must point at a loopback host. Any remote host,
   replica-set member or ``mongodb+srv`` URI is refused before a connection is
   opened, so this script can never touch a shared/production database.
2. Unless ``--no-backup`` is passed, every collection is exported to
   ``db_backups/pre_reset_<timestamp>/<database>/<collection>.json`` first
   (MongoDB Extended JSON, readable by ``bson.json_util``). The dump directory
   is git-ignored.
3. ``--yes`` is required. Without it the script only prints what it would do.

Usage (from ``PLACER/backend``)::

    .venv\\Scripts\\python.exe -m scripts.reset_db --yes
    .venv\\Scripts\\python.exe -m scripts.reset_db --yes --no-backup
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from bson.json_util import RELAXED_JSON_OPTIONS, dumps  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo.uri_parser import parse_uri  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import mongodb  # noqa: E402

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class UnsafeTargetError(RuntimeError):
    pass


def assert_local_uri(uri: str) -> list[str]:
    """Refuse anything that is not a plain loopback MongoDB deployment."""
    if uri.startswith("mongodb+srv://"):
        raise UnsafeTargetError(
            "Refusing to reset a mongodb+srv:// target: it is never a local database."
        )
    try:
        parsed = parse_uri(uri)
    except Exception as exc:  # noqa: BLE001 - malformed URI is also unsafe
        raise UnsafeTargetError(f"Cannot parse MONGODB_URI: {exc}") from exc
    hosts = [host for host, _port in parsed["nodelist"]]
    if not hosts:
        raise UnsafeTargetError("MONGODB_URI does not contain a host.")
    unsafe = [h for h in hosts if h not in LOOPBACK_HOSTS and not h.startswith("127.")]
    if unsafe:
        raise UnsafeTargetError(
            "Refusing to reset a non-local MongoDB target. Offending host(s): "
            + ", ".join(unsafe)
        )
    return hosts


async def export_backup(db, database: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = Path("db_backups") / f"pre_reset_{stamp}" / database
    target.mkdir(parents=True, exist_ok=True)

    collections = [
        name for name in await db.list_collection_names() if not name.startswith("system.")
    ]
    for name in sorted(collections):
        documents = await db[name].find({}).to_list(length=None)
        (target / f"{name}.json").write_text(
            dumps(documents, json_options=RELAXED_JSON_OPTIONS), encoding="utf-8"
        )
        print(f"  backed up {name:<28} {len(documents):>6} document(s)")
    print(f"Backup written to {target}")
    return target


async def reset(args: argparse.Namespace) -> int:
    settings = get_settings()
    database = settings.MONGODB_DB_NAME
    uri = settings.MONGODB_URI

    try:
        hosts = assert_local_uri(uri)
    except UnsafeTargetError as exc:
        print(f"REFUSED: {exc}")
        return 2

    print(f"Target : {database}")
    print(f"Host(s): {', '.join(hosts)}")
    if not args.yes:
        print("\nDry run. Re-run with --yes to drop the database.")
        return 0

    client = AsyncIOMotorClient(uri)
    db = client[database]
    try:
        await client.admin.command("ping")
        if not args.no_backup:
            print("\nBacking up existing collections:")
            await export_backup(db, database)
        else:
            print("\nSkipping backup (--no-backup).")

        print(f"\nDropping database {database!r} ...")
        await client.drop_database(database)

        # Recreate the schema indexes the application expects.
        mongodb.client = client
        mongodb.db = db
        from app.core.database import ensure_indexes, ensure_market_indexes

        await ensure_indexes()
        await ensure_market_indexes(db)

        names = sorted(await db.list_collection_names())
        print(f"Reset complete. Collections created: {len(names)}")
        return 0
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Drop and recreate the local PLACER database.")
    parser.add_argument("--yes", action="store_true", help="Actually drop the database.")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the JSON export (only safe when a verified backup already exists).",
    )
    return asyncio.run(reset(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
