"""Canonical academic departments.

The placement database stores departments as free text, which let the same
department accumulate several spellings ("CS", "Computer Science",
"Computer Science & Engineering"). That is not only a display problem: a
drive that requires ``Computer Science`` will reject a student whose profile
says ``CS`` even though they are in the same department, which blocks
applications and every downstream workflow (screening, shortlisting,
analytics).

This module is the single source of truth for department values:

* :func:`normalize_department` canonicalises one value for WRITING. It maps
  known aliases onto the canonical label and preserves genuinely unknown free
  text, so no real information is destroyed.
* :func:`department_label` canonicalises one value for DISPLAY/AGGREGATION and
  turns a blank value into the explicit ``Not specified`` bucket.
* :func:`department_matches` compares a student's department with a drive's
  eligible departments using the same rules on both sides, so an alias can
  never silently exclude an eligible student.

The canonical labels are the values already present in MongoDB (the
department values the existing drives were created with). No record is
rewritten automatically; legacy rows are normalised on read, and new writes
store the canonical label. ``scripts/normalize_departments.py`` performs an
auditable, dry-run-first migration if the operator chooses to rewrite them.
"""
from __future__ import annotations

# Departments that exist as canonical values in the placement database plus
# the standard engineering streams a college placement cell may add. Order is
# meaningful: it is the order the UI pickers present.
CANONICAL_DEPARTMENTS: tuple[str, ...] = (
    "Computer Science",
    "Information Technology",
    "Electronics and Communication",
    "Electrical Engineering",
    "Mechanical Engineering",
    "Civil Engineering",
    "Mathematics and Computing",
    "Artificial Intelligence and Machine Learning",
    "Data Science",
    "Statistics",
)

# Alias -> canonical label. Keys are lower-cased, ``&`` normalised to ``and``,
# punctuation removed and whitespace collapsed (see ``_alias_key``).
_DEPARTMENT_ALIASES: dict[str, str] = {
    # Computer Science
    "cs": "Computer Science",
    "cse": "Computer Science",
    "comp sci": "Computer Science",
    "compsci": "Computer Science",
    "computer science": "Computer Science",
    "computer sciences": "Computer Science",
    "computer science and engineering": "Computer Science",
    "computer science engineering": "Computer Science",
    "computer science and engg": "Computer Science",
    "computer engineering": "Computer Science",
    "b tech cse": "Computer Science",
    "btech cse": "Computer Science",
    # Information Technology
    "it": "Information Technology",
    "information tech": "Information Technology",
    "information technology": "Information Technology",
    "information technology engineering": "Information Technology",
    "b tech it": "Information Technology",
    "btech it": "Information Technology",
    # Electronics and Communication (the canonical DB value is NOT the long
    # "... Engineering" form, so every alias must land on this exact label).
    "ece": "Electronics and Communication",
    "ec": "Electronics and Communication",
    "electronics": "Electronics and Communication",
    "electronics and communication": "Electronics and Communication",
    "electronics and communication engineering": "Electronics and Communication",
    "electronics and communications": "Electronics and Communication",
    "electronics and communication engg": "Electronics and Communication",
    "electronics and telecommunication": "Electronics and Communication",
    "electronics and telecommunication engineering": "Electronics and Communication",
    # Electrical Engineering
    "ee": "Electrical Engineering",
    "eee": "Electrical Engineering",
    "electrical": "Electrical Engineering",
    "electrical engineering": "Electrical Engineering",
    "electrical and electronics engineering": "Electrical Engineering",
    "electrical and electronics": "Electrical Engineering",
    "electrical engg": "Electrical Engineering",
    # Mechanical Engineering
    "me": "Mechanical Engineering",
    "mech": "Mechanical Engineering",
    "mechanical": "Mechanical Engineering",
    "mechanical engineering": "Mechanical Engineering",
    "mechanical engg": "Mechanical Engineering",
    # Civil Engineering
    "ce": "Civil Engineering",
    "civil": "Civil Engineering",
    "civil engineering": "Civil Engineering",
    # Mathematics and Computing
    "mnc": "Mathematics and Computing",
    "maths and computing": "Mathematics and Computing",
    "math and computing": "Mathematics and Computing",
    "mathematics and computing": "Mathematics and Computing",
    "mathematics computing": "Mathematics and Computing",
    "mathematics and computer science": "Mathematics and Computing",
    # AI / ML
    "aiml": "Artificial Intelligence and Machine Learning",
    "ai ml": "Artificial Intelligence and Machine Learning",
    "ai and ml": "Artificial Intelligence and Machine Learning",
    "artificial intelligence": "Artificial Intelligence and Machine Learning",
    "artificial intelligence and machine learning": "Artificial Intelligence and Machine Learning",
    "artificial intelligence and machine learning engineering": "Artificial Intelligence and Machine Learning",
    # Data Science
    "ds": "Data Science",
    "data science": "Data Science",
    "data science and engineering": "Data Science",
    # Statistics
    "stats": "Statistics",
    "statistics": "Statistics",
    "applied statistics": "Statistics",
}

# Explicit display bucket for a missing department. Kept separate from
# ``normalize_department`` (which returns ``None``) so a write can never store
# the placeholder as if it were a real department.
NOT_SPECIFIED_DEPARTMENT = "Not specified"


def _alias_key(value: str) -> str:
    text = " ".join(value.split()).lower().replace("&", " and ").replace(".", " ")
    text = text.replace("(", " ").replace(")", " ").replace(",", " ")
    return " ".join(text.split())


def normalize_department(value: str | None) -> str | None:
    """Canonicalise one department value for storage.

    Returns ``None`` for a blank value, the canonical label for a known alias,
    and the trimmed original text for anything unrecognised. Never raises and
    never invents a department.
    """
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return _DEPARTMENT_ALIASES.get(_alias_key(text), text)


def department_label(value: str | None) -> str:
    """Canonicalise one department value for display/aggregation.

    A blank value becomes the single explicit ``Not specified`` bucket so it
    is counted rather than silently dropped from a chart.
    """
    return normalize_department(value) or NOT_SPECIFIED_DEPARTMENT


def normalize_departments(values: list[str] | None) -> list[str]:
    """Canonicalise a list of departments, dropping blanks and duplicates.

    Order is preserved so a TPO's chosen order is not reshuffled.
    """
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        normalized = normalize_department(value)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def department_matches(student_department: str | None, eligible_departments: list[str] | None) -> bool:
    """Whether a student's department satisfies a drive's department criteria.

    An empty/absent eligibility list means "open to all departments". Both
    sides are canonicalised before comparison, and a raw case-insensitive
    equality check is kept as a final fallback so an unrecognised but
    identically-spelled value still matches.
    """
    eligible = [value for value in (eligible_departments or []) if value and str(value).strip()]
    if not eligible:
        return True

    student_key = normalize_department(student_department)
    student_raw = " ".join(str(student_department or "").split()).lower()
    for candidate in eligible:
        candidate_key = normalize_department(candidate)
        if student_key and candidate_key and student_key.lower() == candidate_key.lower():
            return True
        candidate_raw = " ".join(str(candidate).split()).lower()
        if student_raw and student_raw == candidate_raw:
            return True
    return False
