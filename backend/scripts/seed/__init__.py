"""Deterministic, idempotent seed package for the PLACER placement database.

Run through :mod:`scripts.seed.run_all`; each module can also be executed on
its own for debugging. The package only writes to the MongoDB instance named
by ``MONGODB_URI`` / ``MONGODB_DB_NAME`` and refuses to touch a remote host
(see ``scripts/reset_db.py`` and ``run_all.py``).
"""
