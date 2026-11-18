"""Unit tests for the public job-board importer.

These cover the honesty guarantees the importer exists to provide: text is
kept faithful to the source, job families are only assigned on explicit
evidence, and every imported posting keeps its provenance. No network access
is used.
"""
from dataclasses import replace

import httpx
import pytest

from app.models.market import JobFamily
from app.services.market_import_service import (
    ADAPTERS,
    MarketImportService,
    _classify_job_family,
    _clean_text,
    _json_payload,
    _remoteok_normalise,
    _repair_mojibake,
)


def test_json_payload_decodes_utf8_despite_latin1_charset():
    body = '{"position": "Senior Engineer \u2014 Platform"}'.encode("utf-8")
    response = httpx.Response(
        200,
        content=body,
        headers={"content-type": "application/json; charset=latin-1"},
    )
    assert _json_payload(response)["position"] == "Senior Engineer \u2014 Platform"


def test_repair_mojibake_only_touches_double_encoded_text():
    # UTF-8 bytes for "’" decoded as latin-1 leave C1 control characters.
    assert _repair_mojibake("Sotheby\u00e2\u0080\u0099s") == "Sotheby\u2019s"
    # Ordinary non-ASCII text must be returned untouched.
    assert _repair_mojibake("Zürich") == "Zürich"


def test_clean_text_strips_html_and_repairs_mojibake():
    assert _clean_text("<p>Build <b>APIs</b>\u00e2\u0080\u0094 fast</p>") == (
        "Build APIs \u2014 fast"
    )


def test_title_keyword_is_authoritative_for_job_family():
    assert (
        _classify_job_family("Senior Data Engineer", ["machine learning", "mlops"])
        == JobFamily.DATA_ANALYTICS
    )
    assert _classify_job_family("UI Developer", []) == JobFamily.FRONTEND_ENGINEERING
    assert _classify_job_family("ML Inference Engineer", []) == JobFamily.AI_ML


def test_tag_only_evidence_needs_two_keywords_from_the_same_family():
    assert _classify_job_family("Accountant", ["machine learning"]) is None
    assert _classify_job_family("Accountant", ["excel", "rest"]) is None
    assert (
        _classify_job_family("Accountant", ["machine learning", "mlops"])
        == JobFamily.AI_ML
    )


def test_remoteok_normalise_keeps_provenance_and_skips_unclassifiable_rows():
    raw = {
        "id": 123,
        "date": "2026-11-10T00:00:00+00:00",
        "position": "Data Engineer",
        "company": "Acme",
        "location": "Berlin",
        "description": "<p>Build pipelines with Python and SQL.</p>",
        "tags": ["python", "sql"],
        "url": "https://remoteok.com/remote-jobs/123",
    }
    document = _remoteok_normalise(raw, "remoteok-2026.11.18", "2026-11-18T12:00:00")

    assert document is not None
    assert document["job_family"] == JobFamily.DATA_ANALYTICS
    assert document["source"] == "remoteok"
    assert document["source_url"] == "https://remoteok.com/remote-jobs/123"
    assert document["source_license"]
    assert document["imported_at"].isoformat() == "2026-11-18T12:00:00"
    assert document["_raw_description"] == "Build pipelines with Python and SQL."

    assert (
        _remoteok_normalise(
            {**raw, "position": "Accountant"}, "v", "2026-11-18T12:00:00"
        )
        is None
    )
    assert (
        _remoteok_normalise(
            {**raw, "description": ""}, "v", "2026-11-18T12:00:00"
        )
        is None
    )


@pytest.mark.asyncio
async def test_import_dry_run_and_dedupe_write_audit_rows(mock_mongo):
    raw = {
        "id": 456,
        "date": "2026-11-10T00:00:00+00:00",
        "position": "Data Engineer",
        "company": "Acme",
        "location": "Berlin",
        "description": "<p>Build pipelines with Python and SQL.</p>",
        "tags": ["python", "sql"],
        "url": "https://remoteok.com/remote-jobs/456",
    }

    async def fake_fetch(_client):
        return [raw, dict(raw)]

    original = ADAPTERS["remoteok"]
    ADAPTERS["remoteok"] = replace(original, fetch=fake_fetch)
    try:
        service = MarketImportService(mock_mongo)

        dry = await service.import_source("remoteok", dry_run=True)
        assert dry.status == "success"
        assert dry.fetched == 2
        assert dry.imported == 1
        assert dry.duplicates == 1
        assert await mock_mongo.job_market_postings.count_documents({}) == 0

        real = await service.import_source("remoteok")
        assert real.imported == 1
        stored = await mock_mongo.job_market_postings.find_one({"external_id": "remoteok-456"})
        assert stored is not None
        assert stored["source_url"] == "https://remoteok.com/remote-jobs/456"
        assert stored["source_license"]
        assert stored["imported_at"] is not None

        again = await service.import_source("remoteok")
        assert again.imported == 0
        assert again.duplicates == 2
    finally:
        ADAPTERS["remoteok"] = original

    runs = [row async for row in mock_mongo.market_import_runs.find({})]
    assert len(runs) == 3
    assert all(row["source"] == "remoteok" for row in runs)
    assert runs[0]["notes"] == "Dry run: no postings were written."
    assert runs[1]["notes"] is None
