"""Registry of job-market data sources.

The market analytics dataset can contain two very different things:

* the curated **demo** dataset (``source="mock"``), which is fictional and must
  never be presented as real hiring statistics; and
* **genuinely imported public postings** from documented APIs, which carry
  their own source id plus ``source_url`` / ``source_license`` / ``imported_at``
  provenance on every document.

This module is the single place that maps a source id to a human label,
homepage and licence/attribution string. The analytics service uses it to
build honest response metadata; the frontend renders that metadata verbatim.
Unknown ids (e.g. a user-supplied file import with a custom id) fall back to a
neutral label rather than pretending to be mock or inventing a licence.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketSourceDefinition:
    id: str
    label: str
    is_mock: bool
    homepage: str | None
    license: str | None
    attribution: str


MARKET_SOURCES: dict[str, MarketSourceDefinition] = {
    "mock": MarketSourceDefinition(
        id="mock",
        label="PLACER demo dataset",
        is_mock=True,
        homepage=None,
        license="Fictional demo data generated for PLACER.",
        attribution="PLACER fictional mock job-market dataset.",
    ),
    "remoteok": MarketSourceDefinition(
        id="remoteok",
        label="RemoteOK public API",
        is_mock=False,
        homepage="https://remoteok.com",
        license="Public RemoteOK API; see https://remoteok.com/legal for terms.",
        attribution="Job postings from the RemoteOK public API (remoteok.com).",
    ),
    "arbeitnow": MarketSourceDefinition(
        id="arbeitnow",
        label="Arbeitnow public job board API",
        is_mock=False,
        homepage="https://www.arbeitnow.com",
        license=(
            "Public Arbeitnow job-board API; see "
            "https://www.arbeitnow.com for terms."
        ),
        attribution="Job postings from the Arbeitnow public job-board API.",
    ),
    "hn_hiring": MarketSourceDefinition(
        id="hn_hiring",
        label="Hacker News 'Who is hiring?' archive",
        is_mock=False,
        homepage="https://news.ycombinator.com",
        license=(
            "Public Hacker News comments accessed via the Algolia HN Search "
            "API; see https://news.ycombinator.com/legal and "
            "https://www.algolia.com/policies/terms/."
        ),
        attribution=(
            "Hiring posts from the monthly Hacker News 'Ask HN: Who is "
            "hiring?' threads (news.ycombinator.com) via the Algolia HN "
            "Search API."
        ),
    ),
}

def source_definition(source_id: str) -> MarketSourceDefinition:
    """Registry entry for ``source_id``, with an honest fallback for new ids."""
    known = MARKET_SOURCES.get(source_id)
    if known is not None:
        return known
    # Never invent a licence for a source we do not know: report that the
    # licence is unknown instead.
    return MarketSourceDefinition(
        id=source_id,
        label=f"Imported source ({source_id})",
        is_mock=False,
        homepage=None,
        license=None,
        attribution=f"Imported public postings with source id '{source_id}'.",
    )


def is_mock_source(source_id: str) -> bool:
    return source_definition(source_id).is_mock


def source_label(source_id: str) -> str:
    return source_definition(source_id).label


def source_attribution(source_ids: list[str]) -> str:
    """Comma-separated attribution text for the given exact source ids."""
    labels = [source_definition(source_id).attribution for source_id in source_ids]
    return " ".join(labels)
