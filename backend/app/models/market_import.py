"""Audit records for job-market import runs.

Every import (real API or user-supplied file) writes one document so the
provenance of the analytics dataset is always explainable: which endpoint was
called, when, how many postings were fetched/imported/skipped, and why rows
were rejected. The audit collection is append-only from the application's
perspective; it never feeds the analytics aggregates.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.base import MongoBaseModel

ImportStatus = Literal["success", "partial", "failed"]


class MarketImportRunInDB(MongoBaseModel):
    source: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,49}$")
    endpoint: str | None = Field(default=None, max_length=1000)
    dataset_version: str = Field(min_length=1, max_length=100)
    status: ImportStatus
    started_at: datetime
    finished_at: datetime | None = None
    fetched: int = Field(default=0, ge=0)
    imported: int = Field(default=0, ge=0)
    duplicates: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=2000)


class MarketImportRunResponse(BaseModel):
    """Public summary of one audit record (no raw payloads)."""

    id: str
    source: str
    endpoint: str | None
    dataset_version: str
    status: ImportStatus
    started_at: datetime
    finished_at: datetime | None
    fetched: int
    imported: int
    duplicates: int
    skipped: int
    errors: list[str]
    notes: str | None
