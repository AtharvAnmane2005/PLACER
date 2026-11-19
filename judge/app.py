"""Isolated code-execution judge.

The backend never runs student code itself when ``CODE_EXECUTION_BACKEND=judge``.
It POSTs one submission here and receives the same ``CodeRunSummary`` shape the
local runner produces. This service reuses that exact runner (copied into the
image from ``backend/app``) with ``CODE_EXECUTION_BACKEND`` forced to ``local``,
so there is one grading implementation, not two.

The container is the security boundary: no network, read-only root filesystem,
tmpfs-only writes, non-root user, dropped capabilities, CPU/memory/pids limits.

Note: this module deliberately does **not** use ``from __future__ import
annotations``. FastAPI/Pydantic resolve request-model annotations by looking
the defining module up in ``sys.modules``; string annotations make that fail
when the module is loaded dynamically (as tests do).
"""
import os
import threading

# Force local execution *before* the shared runner imports settings. Without
# this a misconfigured deployment could make the judge call itself forever.
os.environ["CODE_EXECUTION_BACKEND"] = "local"
os.environ.setdefault("CODE_EXECUTION_ENABLED", "true")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app.models.assessment import TestCase  # noqa: E402
from app.services.code_execution_service import (  # noqa: E402
    execute_code,
    supported_languages,
)

app = FastAPI(title="PLACER Judge", version="1.0.0", docs_url=None, redoc_url=None)

# One CPU-limited container cannot usefully run many submissions at once; the
# semaphore turns overload into a clear 503 instead of a timeout storm.
_MAX_CONCURRENT_RUNS = int(os.environ.get("JUDGE_MAX_CONCURRENT_RUNS", "2"))
_slots = threading.BoundedSemaphore(_MAX_CONCURRENT_RUNS)


class RunRequest(BaseModel):
    language: str | None = None
    code: str = Field(max_length=20_000)
    test_cases: list[TestCase] = Field(default_factory=list, max_length=20)
    only_visible: bool = False


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "languages": supported_languages()}


@app.post("/run")
def run(payload: RunRequest) -> dict:
    if not _slots.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Judge is busy; retry shortly.")
    try:
        summary = execute_code(
            payload.language,
            payload.code,
            payload.test_cases,
            only_visible=payload.only_visible,
        )
        return summary.model_dump(mode="json")
    finally:
        _slots.release()
