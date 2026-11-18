"""Audit and (optionally) canonicalise department values in MongoDB.

The application now normalises departments on read and on write, so no data
migration is required for the product to behave correctly. This script exists
for operators who want the stored documents themselves to use one spelling.

It is a DRY RUN by default: it prints exactly what would change and writes
nothing. Pass ``--apply`` to persist the changes.

What it touches:

* ``students.department`` — one canonical label (or left untouched when the
  value is unknown free text).
* ``tpos.department_scope`` — each entry canonicalised, blanks/dedupes removed.
* ``placement_drives.eligibility.departments`` — each entry canonicalised.

Nothing is deleted. A blank department stays blank (it is displayed as
"Not specified" at read time); unknown free text is preserved verbatim.

Usage (from backend/, with the venv active):
    python -m scripts.normalize_departments
    python -m scripts.normalize_departments --apply
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter

from app.core.database import close_mongo_connection, connect_to_mongo, get_database
from app.core.departments import normalize_department, normalize_departments


async def _audit_students(db, apply: bool) -> tuple[int, Counter]:
    changes: Counter = Counter()
    updated = 0
    async for student in db.students.find({}, {"department": 1}):
        current = student.get("department")
        normalized = normalize_department(current)
        if normalized == current:
            continue
        changes[f"{current!r} -> {normalized!r}"] += 1
        if apply:
            await db.students.update_one({"_id": student["_id"]}, {"$set": {"department": normalized}})
        updated += 1
    return updated, changes


async def _audit_tpos(db, apply: bool) -> tuple[int, Counter]:
    changes: Counter = Counter()
    updated = 0
    async for tpo in db.tpos.find({}, {"department_scope": 1}):
        current = tpo.get("department_scope") or []
        normalized = normalize_departments(current)
        if normalized == current:
            continue
        changes[f"{current!r} -> {normalized!r}"] += 1
        if apply:
            await db.tpos.update_one({"_id": tpo["_id"]}, {"$set": {"department_scope": normalized}})
        updated += 1
    return updated, changes


async def _audit_drives(db, apply: bool) -> tuple[int, Counter]:
    changes: Counter = Counter()
    updated = 0
    async for drive in db.placement_drives.find({}, {"eligibility.departments": 1}):
        eligibility = drive.get("eligibility") or {}
        current = eligibility.get("departments") or []
        normalized = normalize_departments(current)
        if normalized == current:
            continue
        changes[f"{current!r} -> {normalized!r}"] += 1
        if apply:
            await db.placement_drives.update_one(
                {"_id": drive["_id"]},
                {"$set": {"eligibility.departments": normalized}},
            )
        updated += 1
    return updated, changes


def _print_section(title: str, updated: int, changes: Counter, apply: bool) -> None:
    verb = "updated" if apply else "would update"
    print(f"\n{title}: {updated} document(s) {verb}")
    for change, count in changes.most_common():
        print(f"  {count:>4}  {change}")


async def _run(apply: bool) -> None:
    await connect_to_mongo()
    try:
        db = get_database()
        students_updated, student_changes = await _audit_students(db, apply)
        tpos_updated, tpo_changes = await _audit_tpos(db, apply)
        drives_updated, drive_changes = await _audit_drives(db, apply)

        _print_section("Students", students_updated, student_changes, apply)
        _print_section("TPOs", tpos_updated, tpo_changes, apply)
        _print_section("Placement drives", drives_updated, drive_changes, apply)

        total = students_updated + tpos_updated + drives_updated
        if not apply and total:
            print("\nDry run only. Re-run with --apply to persist these changes.")
        elif apply:
            print(f"\nApplied canonical departments to {total} document(s).")
        else:
            print("\nEvery stored department is already canonical.")
    finally:
        await close_mongo_connection()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Canonicalise department values in MongoDB (dry run by default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the changes. Without this flag the script only reports them.",
    )
    args = parser.parse_args()
    asyncio.run(_run(apply=args.apply))


if __name__ == "__main__":
    main()
