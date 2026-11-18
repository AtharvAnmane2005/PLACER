"""Import genuinely public job postings into the market-intelligence dataset.

Only documented public APIs are used, and every imported document keeps its
provenance (``source``, ``source_url``, ``source_license``, ``imported_at``).
Nothing is inferred beyond what the posting states:

* the company name, title, location, posting date, tags and description come
  straight from the API payload;
* skills are matched against the existing curated catalog (name/alias tags,
  title tokens, and unambiguous description tokens) — no new skills are
  invented;
* job family is assigned only when the title/tags contain an explicit
  family keyword; unclassifiable postings are skipped;
* fields the API does not publish (company size/HQ/website, salary, minimum
  CGPA, education level, experience) stay ``None``.

Every run writes one ``market_import_runs`` audit document, including dry
runs, so the dataset's provenance is always explainable.
"""
from __future__ import annotations

import asyncio
import calendar
import html
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.market import (
    HiringType,
    JobFamily,
    JobMarketPostingInDB,
    MarketSkillCatalogInDB,
    WorkMode,
)
from app.repositories.job_posting_repository import (
    JobMarketPostingRepository,
    MarketSkillCatalogRepository,
)
from app.repositories.market_import_repository import MarketImportRunRepository
from app.services.market_sources import source_definition

logger = logging.getLogger(__name__)

REMOTEOK_URL = "https://remoteok.com/api"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
ARBEITNOW_MAX_PAGES = 3
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
HN_STORY_QUERY = "Ask HN: Who is hiring?"
HN_CONCURRENCY = 6
HN_MAX_PAGES = 20

_MAX_DESCRIPTION_CHARS = 20_000
_MAX_ERRORS = 25

# Short or ambiguous tokens that must not be matched inside free-text
# descriptions (they are still matched in explicit tags and titles).
_DESCRIPTION_DENYLIST = {
    "rest",
    "node",
    "soap",
    "excel",
}

# Ordered by specificity: earlier families win a tie. A title keyword is
# authoritative; tag-only evidence needs at least two distinct keywords from
# the same family because job boards tag postings with unrelated skills.
_JOB_FAMILY_KEYWORDS: list[tuple[JobFamily, tuple[str, ...]]] = [
    (
        JobFamily.AI_ML,
        (
            "machine learning",
            "ml engineer",
            "mlops",
            "data scientist",
            "ai engineer",
            "artificial intelligence",
            "deep learning",
            "computer vision",
            "nlp engineer",
            "llm engineer",
            "generative ai",
            "ml inference",
            "prompt engineering",
        ),
    ),
    (
        JobFamily.CYBERSECURITY,
        (
            "cybersecurity",
            "cyber security",
            "security engineer",
            "security analyst",
            "infosec",
            "penetration tester",
            "penetration test",
            "appsec",
            "devsecops",
            "soc analyst",
        ),
    ),
    (
        JobFamily.CLOUD_DEVOPS,
        (
            "devops",
            "site reliability",
            "sre",
            "cloud engineer",
            "cloud architect",
            "platform engineer",
            "infrastructure engineer",
            "kubernetes",
            "terraform",
        ),
    ),
    (
        JobFamily.QA_AUTOMATION,
        (
            "quality assurance",
            "qa engineer",
            "qa analyst",
            "test engineer",
            "test automation",
            "automation engineer",
            "sdet",
            "tester",
        ),
    ),
    (
        JobFamily.DATA_ANALYTICS,
        (
            "data analyst",
            "data analytics",
            "business intelligence",
            "bi developer",
            "data engineer",
            "analytics engineer",
            "data warehouse",
            "etl developer",
            "reporting analyst",
            "data architect",
            "data scientist",
        ),
    ),
    (
        JobFamily.BUSINESS_ANALYSIS,
        (
            "business analyst",
            "product analyst",
            "requirements analyst",
            "scrum master",
            "agile coach",
        ),
    ),
    (
        JobFamily.EMBEDDED_ROBOTICS,
        (
            "embedded",
            "firmware",
            "robotics",
            "hardware engineer",
            "iot engineer",
        ),
    ),
    (
        JobFamily.FRONTEND_ENGINEERING,
        (
            "frontend",
            "front-end",
            "front end",
            "react developer",
            "react engineer",
            "vue developer",
            "angular developer",
            "ui engineer",
            "ui developer",
            "web developer",
            "web engineer",
        ),
    ),
    (
        JobFamily.BACKEND_ENGINEERING,
        (
            "backend",
            "back-end",
            "back end",
            "api engineer",
            "node developer",
            "node.js developer",
            "java developer",
            "python developer",
            "golang developer",
            "django developer",
            "rails developer",
            "microservices",
        ),
    ),
    (
        JobFamily.SOFTWARE_ENGINEERING,
        (
            "software engineer",
            "software developer",
            "full stack",
            "fullstack",
            "full-stack",
            "application developer",
            "programmer",
            "technical lead",
            "engineering manager",
            "solutions architect",
            "software architect",
            "android engineer",
            "ios engineer",
            "mobile engineer",
            "software entwickler",
            "softwareentwickler",
        ),
    ),
]


@dataclass
class ImportResult:
    source: str
    dataset_version: str
    status: str
    fetched: int = 0
    imported: int = 0
    duplicates: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "dataset_version": self.dataset_version,
            "status": self.status,
            "fetched": self.fetched,
            "imported": self.imported,
            "duplicates": self.duplicates,
            "skipped": self.skipped,
            "errors": list(self.errors),
            "dry_run": self.dry_run,
        }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "unknown-company"


def _repair_mojibake(value: str) -> str:
    """Undo text that a source double-encoded as UTF-8 bytes in latin-1.

    RemoteOK stores some titles/company names that way ("Sothebyâ€™s" instead
    of "Sotheby’s"), which is visible as C1 control characters (U+0080–U+009F)
    in the JSON. Only that unambiguous signature is repaired; text without it
    is returned untouched so legitimate non-ASCII content is never rewritten.
    """
    if not any("\u0080" <= char <= "\u009f" for char in value):
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    if "\ufffd" in repaired or any("\u0080" <= char <= "\u009f" for char in repaired):
        return value
    return repaired


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return _repair_mojibake(re.sub(r"\s+", " ", text).strip())


def _normalise_token(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO string or a seconds/milliseconds epoch into naive UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e11:  # milliseconds
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return _parse_datetime(int(raw))
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    return None


def _matches(text: str, token: str) -> bool:
    if not text or not token:
        return False
    pattern = r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _classify_job_family(title: str, tags: list[str]) -> JobFamily | None:
    """Assign a job family only when the posting states it clearly.

    A keyword in the job TITLE is authoritative. Tags are unreliable (job
    boards routinely attach unrelated skill tags), so tag-only evidence needs
    at least two distinct keywords from the same family. Postings with no
    clear signal are skipped rather than guessed into a family.
    """
    title_text = title.casefold()
    for family, keywords in _JOB_FAMILY_KEYWORDS:
        if any(_matches(title_text, keyword) for keyword in keywords):
            return family

    tag_text = " ".join(tags).casefold()
    best: tuple[int, JobFamily] | None = None
    for family, keywords in _JOB_FAMILY_KEYWORDS:
        hits = sum(1 for keyword in keywords if _matches(tag_text, keyword))
        if hits >= 2 and (best is None or hits > best[0]):
            best = (hits, family)
    return best[1] if best is not None else None


def _infer_hiring_type(job_types: list[str] | None) -> HiringType | None:
    for job_type in job_types or []:
        normalised = job_type.casefold().replace("_", "-").strip()
        if "intern" in normalised:
            return HiringType.INTERNSHIP
        if normalised in {"full-time", "full time", "permanent", "fulltime"}:
            return HiringType.FULL_TIME
    return None


class _SkillMatcher:
    """Match posting text against the existing curated skill catalog."""

    def __init__(self, catalog: list[MarketSkillCatalogInDB]):
        self.entries = catalog
        self.by_tag: dict[str, MarketSkillCatalogInDB] = {}
        self.tokens: dict[str, list[str]] = {}
        for entry in catalog:
            tokens = [entry.name, *entry.aliases]
            self.tokens[entry.name] = [token for token in tokens if token.strip()]
            for token in tokens:
                key = _normalise_token(token)
                if key:
                    self.by_tag.setdefault(key, entry)

    def extract(
        self, title: str, tags: list[str], description: str
    ) -> tuple[list[str], list[str]]:
        found: dict[str, MarketSkillCatalogInDB] = {}

        # 1. Explicit tags: exact catalog/alias match only.
        for tag in tags:
            entry = self.by_tag.get(_normalise_token(tag))
            if entry is not None:
                found[entry.name] = entry

        # 2. Title: any catalog name/alias of at least 2 characters.
        for entry in self.entries:
            if entry.name in found:
                continue
            for token in self.tokens.get(entry.name, []):
                if len(token.strip()) >= 2 and _matches(title, token):
                    found[entry.name] = entry
                    break

        # 3. Description: only unambiguous tokens of at least 4 characters.
        for entry in self.entries:
            if entry.name in found:
                continue
            for token in self.tokens.get(entry.name, []):
                key = _normalise_token(token)
                if len(key) < 4 or key in _DESCRIPTION_DENYLIST:
                    continue
                if _matches(description, token):
                    found[entry.name] = entry
                    break

        technical = sorted(
            (name for name, entry in found.items() if entry.is_technical),
            key=str.casefold,
        )
        soft = sorted(
            (name for name, entry in found.items() if not entry.is_technical),
            key=str.casefold,
        )
        return technical, soft


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------

RemoteFetcher = Callable[[httpx.AsyncClient], Awaitable[list[dict[str, Any]]]]


def _json_payload(response: httpx.Response) -> Any:
    """Decode a JSON body as UTF-8 regardless of the declared charset.

    RemoteOK serves UTF-8 JSON but its ``Content-Type`` can make HTTP clients
    decode the bytes as latin-1, which corrupts names ("Sotheby’s" becomes
    "Sothebyâ€™s") and titles (em dashes become three characters). Decoding
    the raw bytes as UTF-8 keeps the stored text faithful to the source.
    """
    try:
        return json.loads(response.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return response.json()


async def _fetch_remoteok(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get(REMOTEOK_URL)
    response.raise_for_status()
    payload = _json_payload(response)
    if not isinstance(payload, list):
        raise ValueError("RemoteOK API returned an unexpected payload.")
    # The first element is a legal notice, not a posting.
    return [item for item in payload if isinstance(item, dict) and item.get("id")]


async def _fetch_arbeitnow(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    url: str | None = ARBEITNOW_URL
    for _ in range(ARBEITNOW_MAX_PAGES):
        if not url:
            break
        response = await client.get(url)
        response.raise_for_status()
        payload = _json_payload(response)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ValueError("Arbeitnow API returned an unexpected payload.")
        rows.extend(item for item in data if isinstance(item, dict))
        links = payload.get("links") if isinstance(payload, dict) else None
        url = links.get("next") if isinstance(links, dict) else None
    return rows


@dataclass(frozen=True)
class _SourceAdapter:
    id: str
    endpoint: str
    fetch: RemoteFetcher
    normalise: Callable[[dict[str, Any], str, str], dict[str, Any] | None]


def _remoteok_normalise(
    raw: dict[str, Any], dataset_version: str, imported_at_iso: str
) -> dict[str, Any] | None:
    posted_at = _parse_datetime(raw.get("date") or raw.get("epoch"))
    description = _clean_text(raw.get("description"))
    title = _clean_text(raw.get("position"))
    if posted_at is None or not description or not title:
        return None
    tags = [str(tag) for tag in raw.get("tags") or [] if str(tag).strip()]
    job_family = _classify_job_family(title, tags)
    if job_family is None:
        return None
    company = _clean_text(raw.get("company")) or "Unknown company"
    location = _clean_text(raw.get("location")) or "Remote"
    return {
        "external_id": f"remoteok-{raw.get('id')}",
        "dataset_version": dataset_version,
        "source": "remoteok",
        "source_url": raw.get("url") or raw.get("apply_url"),
        "source_license": source_definition("remoteok").license,
        "imported_at": datetime.fromisoformat(imported_at_iso),
        "company_name": company[:200],
        "company_slug": _slugify(company),
        "company_industry": "Not specified",
        "job_title": title[:200],
        "job_family": job_family,
        "description": description[:_MAX_DESCRIPTION_CHARS],
        "jd_text": description[:_MAX_DESCRIPTION_CHARS],
        "location": location[:100],
        "work_mode": WorkMode.REMOTE,
        "posted_at": posted_at,
        "year": posted_at.year,
        "quarter": (posted_at.month - 1) // 3 + 1,
        "month": posted_at.month,
        "is_active": False,
        "created_at": datetime.fromisoformat(imported_at_iso),
        "_raw_title": title,
        "_raw_tags": tags,
        "_raw_description": description,
    }


def _arbeitnow_normalise(
    raw: dict[str, Any], dataset_version: str, imported_at_iso: str
) -> dict[str, Any] | None:
    posted_at = _parse_datetime(raw.get("created_at"))
    description = _clean_text(raw.get("description"))
    title = _clean_text(raw.get("title"))
    if posted_at is None or not description or not title:
        return None
    tags = [str(tag) for tag in raw.get("tags") or [] if str(tag).strip()]
    job_family = _classify_job_family(title, tags)
    if job_family is None:
        return None
    company = _clean_text(raw.get("company_name")) or "Unknown company"
    location = _clean_text(raw.get("location"))
    remote = bool(raw.get("remote"))
    if not location:
        location = "Remote" if remote else "Not specified"
    return {
        "external_id": f"arbeitnow-{raw.get('slug') or raw.get('url')}",
        "dataset_version": dataset_version,
        "source": "arbeitnow",
        "source_url": raw.get("url"),
        "source_license": source_definition("arbeitnow").license,
        "imported_at": datetime.fromisoformat(imported_at_iso),
        "company_name": company[:200],
        "company_slug": _slugify(company),
        "company_industry": "Not specified",
        "job_title": title[:200],
        "job_family": job_family,
        "hiring_type": _infer_hiring_type(raw.get("job_types")),
        "description": description[:_MAX_DESCRIPTION_CHARS],
        "jd_text": description[:_MAX_DESCRIPTION_CHARS],
        "location": location[:100],
        "work_mode": WorkMode.REMOTE if remote else None,
        "posted_at": posted_at,
        "year": posted_at.year,
        "quarter": (posted_at.month - 1) // 3 + 1,
        "month": posted_at.month,
        "is_active": False,
        "created_at": datetime.fromisoformat(imported_at_iso),
        "_raw_title": title,
        "_raw_tags": tags,
        "_raw_description": description,
    }


_HN_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_HN_ROLE_HINT_RE = re.compile(
    r"\b(engineer|engineering|developer|programmer|scientist|analyst|manager|"
    r"designer|architect|lead|director|intern|consultant|specialist|"
    r"administrator|researcher|devops|sre|recruiter)\b",
    re.IGNORECASE,
)
_HN_IS_HIRING_RE = re.compile(
    r"^(?P<company>.+?)\s+(?:is|are)\s+hiring\s+(?P<role>.+)$", re.IGNORECASE
)
_HN_ROLE_PHRASE_RE = re.compile(
    r"\b((?:[A-Za-z][\w/&+.-]*\s+){0,5}"
    r"(?:engineers?|developers?|scientists?|analysts?|managers?|designers?|"
    r"architects?|leads?|directors?|interns?|consultants?|specialists?|"
    r"administrators?|programmers?|strategists?|researchers?))\b",
    re.IGNORECASE,
)
_HN_ROLE_LEAD_RE = re.compile(
    r"^(?:an?|the|our|we(?:'re| are)?|is|are|hiring|looking\s+for|seeking|"
    r"searching\s+for|experienced|talented|multiple)\s+",
    re.IGNORECASE,
)
_HN_NON_TECH_ROLE_RE = re.compile(
    r"\b(sales|account executive|mechanical|civil|electrical|chemical|"
    r"industrial)\b",
    re.IGNORECASE,
)
_HN_GENERIC_COMPANIES = {
    "remote",
    "anywhere",
    "worldwide",
    "hiring",
    "we're hiring",
    "we are hiring",
    "seeking work",
    "seeking employment",
    "looking for work",
    "job seeker",
    "available for hire",
}

# Fallback classification for HN headers that name a role without one of the
# curated family keywords (e.g. a bare "Engineering" column). Ordered most
# specific first; only the role/header text is inspected, never the full body.
_HN_FAMILY_FALLBACKS: list[tuple[JobFamily, tuple[str, ...]]] = [
    (
        JobFamily.AI_ML,
        (
            "machine learning",
            "artificial intelligence",
            "ml engineer",
            "ai engineer",
            "data scientist",
            "llm",
            "computer vision",
            "nlp",
        ),
    ),
    (
        JobFamily.CYBERSECURITY,
        (
            "cybersecurity",
            "cyber security",
            "security engineer",
            "security analyst",
            "appsec",
            "infosec",
            "penetration",
            "soc analyst",
            "security",
        ),
    ),
    (
        JobFamily.CLOUD_DEVOPS,
        (
            "devops",
            "sre",
            "site reliability",
            "platform engineer",
            "cloud engineer",
            "cloud architect",
            "infrastructure engineer",
            "kubernetes",
            "terraform",
        ),
    ),
    (
        JobFamily.QA_AUTOMATION,
        (
            "quality assurance",
            "qa engineer",
            "qa analyst",
            "test engineer",
            "test automation",
            "sdet",
            "tester",
            "qa ",
        ),
    ),
    (
        JobFamily.DATA_ANALYTICS,
        (
            "data analyst",
            "data analytics",
            "business intelligence",
            "bi developer",
            "data engineer",
            "analytics engineer",
            "data architect",
        ),
    ),
    (
        JobFamily.BUSINESS_ANALYSIS,
        (
            "business analyst",
            "product analyst",
            "product manager",
            "scrum master",
            "agile coach",
        ),
    ),
    (
        JobFamily.EMBEDDED_ROBOTICS,
        (
            "embedded",
            "firmware",
            "robotics",
            "hardware engineer",
            "iot engineer",
        ),
    ),
    (
        JobFamily.FRONTEND_ENGINEERING,
        (
            "frontend",
            "front-end",
            "front end",
            "react developer",
            "react engineer",
            "vue developer",
            "angular developer",
            "ui engineer",
            "ui developer",
            "web developer",
            "web engineer",
        ),
    ),
    (
        JobFamily.BACKEND_ENGINEERING,
        (
            "backend",
            "back-end",
            "back end",
            "api engineer",
            "node developer",
            "java developer",
            "python developer",
            "golang developer",
            "django developer",
            "rails developer",
            "microservices",
        ),
    ),
    (
        JobFamily.SOFTWARE_ENGINEERING,
        (
            "software engineer",
            "software developer",
            "full stack",
            "fullstack",
            "full-stack",
            "engineer",
            "engineering",
            "developer",
            "programmer",
            "technical lead",
            "engineering manager",
            "architect",
        ),
    ),
]


def _hn_months(today: datetime | None = None) -> list[tuple[int, int]]:
    """Months to import: the current year to date plus the two prior years.

    Three calendar years give the dashboard a genuine prior-year comparison
    instead of a single, trendless period.
    """
    today = today or datetime.utcnow()
    months: list[tuple[int, int]] = []
    for year in range(today.year - 2, today.year + 1):
        last_month = today.month if year == today.year else 12
        months.extend((year, month) for month in range(1, last_month + 1))
    return months


async def _hn_search(
    client: httpx.AsyncClient, params: dict[str, Any]
) -> dict[str, Any]:
    response = await client.get(HN_SEARCH_URL, params=params)
    response.raise_for_status()
    payload = _json_payload(response)
    if not isinstance(payload, dict):
        raise ValueError("Algolia HN API returned an unexpected payload.")
    return payload


async def _hn_find_story(
    client: httpx.AsyncClient, year: int, month: int
) -> dict[str, Any] | None:
    start = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())
    if month == 12:
        end = int(datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp())
    else:
        end = int(datetime(year, month + 1, 1, tzinfo=timezone.utc).timestamp())
    payload = await _hn_search(
        client,
        {
            "query": HN_STORY_QUERY,
            "tags": "story",
            "numericFilters": f"created_at_i>={start},created_at_i<{end}",
            "hitsPerPage": 50,
        },
    )
    label = f"{calendar.month_name[month]} {year}".casefold()
    for hit in payload.get("hits") or []:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or "").casefold()
        if "who is hiring" in title and label in title:
            return hit
    return None


async def _hn_story_comments(
    client: httpx.AsyncClient, story_id: str
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    page = 0
    while page < HN_MAX_PAGES:
        payload = await _hn_search(
            client,
            {
                "tags": f"comment,story_{story_id}",
                "hitsPerPage": 1000,
                "page": page,
            },
        )
        hits.extend(hit for hit in payload.get("hits") or [] if isinstance(hit, dict))
        page += 1
        if page >= int(payload.get("nbPages") or 0):
            break
    # Only top-level comments are job postings; replies are discussion.
    return [hit for hit in hits if str(hit.get("parent_id")) == story_id]


async def _fetch_hn_hiring(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Every top-level comment in the monthly "Who is hiring?" threads.

    One thread is published per month; each top-level comment is a hiring
    post. A month that cannot be fetched is logged and skipped so a single
    upstream failure never discards the rest of the archive.
    """
    rows: list[dict[str, Any]] = []
    semaphore = asyncio.Semaphore(HN_CONCURRENCY)

    async def one_month(year: int, month: int) -> None:
        async with semaphore:
            try:
                story = await _hn_find_story(client, year, month)
                if story is None:
                    logger.warning(
                        "No HN hiring thread found for %s %s",
                        calendar.month_name[month],
                        year,
                    )
                    return
                story_id = str(story.get("objectID") or "")
                if not story_id:
                    return
                comments = await _hn_story_comments(client, story_id)
            except Exception as exc:  # one bad month must not abort the archive
                logger.warning(
                    "HN hiring fetch failed for %s %s: %s",
                    calendar.month_name[month],
                    year,
                    exc,
                )
                return
        for comment in comments:
            rows.append(
                {
                    **comment,
                    "_story_id": story_id,
                    "_story_title": story.get("title"),
                }
            )

    await asyncio.gather(*(one_month(year, month) for year, month in _hn_months()))
    return rows


def _hn_split_segments(plain: str) -> list[str]:
    """Split a hiring header on the separators the threads actually use."""
    head = plain[:800]
    if "|" in head:
        parts = re.split(r"\s*\|\s*", head)
    else:
        parts = re.split(r"\s+[—–]\s+|\s+-\s+", head)
    return [
        re.sub(r"\s+", " ", part).strip(" \t#*-–—:;")
        for part in parts
        if part.strip()
    ]


def _hn_clean_company(value: str) -> str:
    """Company name from the first header column, minus URLs/parentheticals."""
    cleaned = _HN_URL_RE.sub(" ", value)
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" \t#*-–—:;,.")


def _hn_family_fallback(text: str) -> JobFamily | None:
    if _HN_NON_TECH_ROLE_RE.search(text):
        return None
    lowered = text.casefold()
    for family, keywords in _HN_FAMILY_FALLBACKS:
        if any(keyword in lowered for keyword in keywords):
            return family
    return None


def _hn_role_title(segment: str) -> str:
    """Reduce a header column to a concise role title.

    Some comments put the whole job advert in the column after the company.
    Using that verbatim as the title would let short, ambiguous tokens in the
    body match skills, so a role phrase is extracted instead; columns with no
    identifiable role are rejected rather than stored as a title.
    """
    title = segment.strip(" \t#*-–—:;,")
    if len(title) > 120:
        match = _HN_ROLE_PHRASE_RE.search(title[:300])
        if match is None:
            return ""
        title = match.group(1)
    for _ in range(3):
        stripped = _HN_ROLE_LEAD_RE.sub("", title).strip()
        if stripped == title:
            break
        title = stripped
    return title[:120]


def _hn_parse_header(
    plain: str,
) -> tuple[str, str, JobFamily, str, bool] | None:
    """Parse ``Company | Role | Location | ...`` from a hiring comment.

    Only what the comment states is used. A posting is skipped when no company
    or no recognisable role can be read, rather than inventing one.
    """
    segments = _hn_split_segments(plain)
    company = _hn_clean_company(segments[0]) if segments else ""
    candidates = [
        segment
        for segment in segments[1:8]
        if not re.fullmatch(r"\s*(?:https?://|www\.)\S+\s*", segment, re.IGNORECASE)
    ]

    role = ""
    role_text = ""
    is_hiring = _HN_IS_HIRING_RE.search(plain[:500])
    if is_hiring:
        role_text = is_hiring.group("role").strip()

    if (
        not company
        or len(company) > 80
        or company.casefold() in _HN_GENERIC_COMPANIES
    ):
        if not is_hiring:
            return None
        company = _hn_clean_company(is_hiring.group("company"))

    if (
        not company
        or len(company) > 80
        or company.casefold() in _HN_GENERIC_COMPANIES
    ):
        return None

    # Prefer a column that names a role; otherwise use the "is hiring" phrase.
    for segment in candidates:
        title = _hn_role_title(segment)
        if title and _classify_job_family(title, []) is not None:
            role = title
            break
    if not role:
        for segment in candidates:
            title = _hn_role_title(segment)
            if title and _HN_ROLE_HINT_RE.search(title):
                role = title
                break
    if not role and role_text:
        role = _hn_role_title(role_text) or role_text[:120]
    if not role:
        return None
    role = role.strip(" \t#*-–—:;,")

    job_family = _classify_job_family(role, []) or _hn_family_fallback(role)
    if job_family is None:
        return None

    location = "Not specified"
    remote = False
    for segment in candidates:
        if re.search(r"\bremote\b", segment, re.IGNORECASE):
            remote = True
            location = segment[:100]
            break
    if not remote:
        for segment in candidates:
            if segment != role and re.match(r"^[A-Z][\w .'-]+,\s*[A-Z]", segment):
                location = segment[:100]
                break

    return company, role, job_family, location, remote


def _hn_normalise(
    raw: dict[str, Any], dataset_version: str, imported_at_iso: str
) -> dict[str, Any] | None:
    object_id = str(raw.get("objectID") or "").strip()
    posted_at = _parse_datetime(raw.get("created_at"))
    plain = _clean_text(raw.get("comment_text"))
    if not object_id or posted_at is None or not plain:
        return None

    parsed = _hn_parse_header(plain)
    if parsed is None:
        return None
    company, title, job_family, location, remote = parsed

    header = plain[:600].casefold()
    if "intern" in header:
        hiring_type = HiringType.INTERNSHIP
    elif "full time" in header or "full-time" in header:
        hiring_type = HiringType.FULL_TIME
    else:
        hiring_type = None

    return {
        "external_id": f"hn-{object_id}",
        "dataset_version": dataset_version,
        "source": "hn_hiring",
        "source_url": f"https://news.ycombinator.com/item?id={object_id}",
        "source_license": source_definition("hn_hiring").license,
        "imported_at": datetime.fromisoformat(imported_at_iso),
        "company_name": company[:200],
        "company_slug": _slugify(company),
        "company_industry": "Not specified",
        "job_title": title[:200],
        "job_family": job_family,
        "hiring_type": hiring_type,
        "description": plain[:_MAX_DESCRIPTION_CHARS],
        "jd_text": plain[:_MAX_DESCRIPTION_CHARS],
        "location": location[:100],
        "work_mode": WorkMode.REMOTE if remote else None,
        "posted_at": posted_at,
        "year": posted_at.year,
        "quarter": (posted_at.month - 1) // 3 + 1,
        "month": posted_at.month,
        "is_active": False,
        "created_at": datetime.fromisoformat(imported_at_iso),
        "_raw_title": title,
        "_raw_tags": [],
        "_raw_description": plain,
    }


ADAPTERS: dict[str, _SourceAdapter] = {
    "remoteok": _SourceAdapter(
        id="remoteok",
        endpoint=REMOTEOK_URL,
        fetch=_fetch_remoteok,
        normalise=_remoteok_normalise,
    ),
    "arbeitnow": _SourceAdapter(
        id="arbeitnow",
        endpoint=ARBEITNOW_URL,
        fetch=_fetch_arbeitnow,
        normalise=_arbeitnow_normalise,
    ),
    "hn_hiring": _SourceAdapter(
        id="hn_hiring",
        endpoint=HN_SEARCH_URL,
        fetch=_fetch_hn_hiring,
        normalise=_hn_normalise,
    ),
}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MarketImportService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.postings = JobMarketPostingRepository(db)
        self.catalog = MarketSkillCatalogRepository(db)
        self.runs = MarketImportRunRepository(db)

    async def import_source(
        self,
        source: str,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> ImportResult:
        adapter = ADAPTERS.get(source)
        if adapter is None:
            raise ValueError(
                f"Unknown import source '{source}'. Known sources: "
                + ", ".join(sorted(ADAPTERS))
            )

        started_at = datetime.utcnow()
        dataset_version = f"{adapter.id}-{started_at:%Y.%m.%d}"
        result = ImportResult(
            source=adapter.id,
            dataset_version=dataset_version,
            status="success",
            dry_run=dry_run,
        )
        errors: list[str] = []

        try:
            raw_rows = await self._fetch(adapter, client)
            result.fetched = len(raw_rows)
            if limit is not None:
                raw_rows = raw_rows[:limit]

            catalog_docs = await self.catalog.find_many(limit=1000)
            matcher = _SkillMatcher(catalog_docs)
            imported_at_iso = started_at.isoformat()

            prepared: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for raw in raw_rows:
                try:
                    document = adapter.normalise(raw, dataset_version, imported_at_iso)
                except Exception as exc:  # defensive: one bad row never aborts a run
                    result.skipped += 1
                    if len(errors) < _MAX_ERRORS:
                        errors.append(f"normalise: {type(exc).__name__}: {exc}")
                    continue
                if document is None:
                    result.skipped += 1
                    continue

                technical, soft = matcher.extract(
                    document.pop("_raw_title"),
                    document.pop("_raw_tags"),
                    document.pop("_raw_description"),
                )
                document["technical_skills"] = technical
                document["soft_skills"] = soft
                document["required_skills"] = technical + soft

                try:
                    JobMarketPostingInDB.model_validate(document)
                except Exception as exc:
                    result.skipped += 1
                    if len(errors) < _MAX_ERRORS:
                        errors.append(
                            f"{document.get('external_id', '?')}: {type(exc).__name__}: {exc}"
                        )
                    continue

                external_id = document["external_id"]
                if external_id in seen_ids:
                    result.duplicates += 1
                    continue
                seen_ids.add(external_id)
                prepared.append(document)

            existing = await self.postings.existing_external_ids(
                [document["external_id"] for document in prepared]
            )
            fresh = [d for d in prepared if d["external_id"] not in existing]
            result.duplicates += len(prepared) - len(fresh)

            if dry_run:
                result.imported = len(fresh)
            else:
                inserted = await self.postings.create_many(fresh)
                result.imported = inserted

            result.errors = errors
            if errors:
                result.status = "partial"
        except Exception as exc:
            logger.exception("Market import from %s failed", adapter.id)
            result.status = "failed"
            result.errors = [f"{type(exc).__name__}: {exc}"]

        await self._record_run(adapter, result, started_at)
        return result

    async def _fetch(
        self, adapter: _SourceAdapter, client: httpx.AsyncClient | None
    ) -> list[dict[str, Any]]:
        headers = {
            "User-Agent": (
                "PLACER-market-import/1.0 "
                "(academic placement analytics; contact: project maintainer)"
            ),
            "Accept": "application/json",
        }
        if client is not None:
            return await adapter.fetch(client)
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers=headers
        ) as owned:
            return await adapter.fetch(owned)

    async def _record_run(
        self,
        adapter: _SourceAdapter,
        result: ImportResult,
        started_at: datetime,
    ) -> None:
        try:
            await self.runs.create(
                {
                    "source": adapter.id,
                    "endpoint": adapter.endpoint,
                    "dataset_version": result.dataset_version,
                    "status": result.status,
                    "started_at": started_at,
                    "finished_at": datetime.utcnow(),
                    "fetched": result.fetched,
                    "imported": result.imported,
                    "duplicates": result.duplicates,
                    "skipped": result.skipped,
                    "errors": result.errors,
                    "notes": "Dry run: no postings were written."
                    if result.dry_run
                    else None,
                }
            )
        except Exception:  # audit failure must never hide the import outcome
            logger.exception("Could not write market import audit record")
