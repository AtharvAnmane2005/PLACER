"""Resume-parsing skill vocabulary.

This module is now a thin compatibility layer over
:mod:`app.core.skill_taxonomy`, which is the single source of truth for the
project's skills. The public names below are preserved so existing imports
(``CANONICAL_SKILLS``, ``ALIASES``, ``SKILL_PATTERN``, ``normalize_skill``,
``extract_skills``) keep working unchanged.

The old 65-term table was duplicated in this file and had drifted from the
keyword reference in ``ML_Keywords_and_Projects.txt``. Adding a skill in one
place now updates resume parsing, drive requirements, question tags and
analytics together.
"""
from app.core.skill_taxonomy import (  # noqa: F401 - re-exported public API
    ALIASES,
    CANONICAL_SKILLS,
    SKILL_PATTERN,
    canonicalize_skills,
    extract_skills,
    normalize_skill,
)

__all__ = [
    "ALIASES",
    "CANONICAL_SKILLS",
    "SKILL_PATTERN",
    "canonicalize_skills",
    "extract_skills",
    "normalize_skill",
]
