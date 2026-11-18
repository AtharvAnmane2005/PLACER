"""
PHASE D — app/services/jd_explanation_service.py (CORRECTED)

Fix from the original draft: MatchingService.score_resume_against_drive()
does NOT take resume_id/drive_id strings — it takes the actual
ResumeInDB/PlacementDriveInDB objects plus a company_name string, and it
returns a plain dict (final_score, semantic_score, skills_score,
experience_score, matched_skills, missing_skills) — not a pydantic model
with attributes. This mirrors exactly how app/routers/matching.py already
calls it.
"""
from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.ml.llm.client import llm_client
from app.ml.llm.exceptions import LLMUnavailableError
from app.ml.rag.knowledge_store import KnowledgeStore
from app.repositories.application_repository import ApplicationRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.drive_repository import PlacementDriveRepository
from app.repositories.resume_repository import ResumeRepository
from app.services.matching_service import MatchingService

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a career coach. You are given an ALREADY-COMPUTED match-score "
    "breakdown (semantic_score, skills_score, experience_score, final_score) "
    "between a student's resume and a job description, a missing_skills list, "
    "and short reference material retrieved for those missing skills. Explain "
    "in the student's own terms what most likely held the score back and give "
    "2-3 concrete, actionable next steps. Do NOT recompute or contradict the "
    "given scores. Ground every claim in the given facts or retrieved "
    "material only — do not invent details about the role or the skills."
)


class JDExplanationResult:
    def __init__(self, breakdown: dict, narrative: str | None):
        self.breakdown = breakdown  # dict: final_score, semantic_score, skills_score, experience_score, matched_skills, missing_skills
        self.narrative = narrative


class JDExplanationService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.matching = MatchingService(db)
        self.knowledge_store = KnowledgeStore(db)
        self.resumes = ResumeRepository(db)
        self.drives = PlacementDriveRepository(db)
        self.companies = CompanyRepository(db)
        self.applications = ApplicationRepository(db)

    async def explain(self, resume_id: str, drive_id: str) -> JDExplanationResult:
        resume = await self.resumes.get_by_id(resume_id)
        if not resume:
            raise ValueError("Resume not found")

        drive = await self.drives.get_by_id(drive_id)
        if not drive:
            raise ValueError("Drive not found")

        company = await self.companies.get_by_id(drive.company_id)
        company_name = company.name if company else "the company"

        # Reuse the canonical matching logic — every number here is traceable
        # to compute_final_score(). If this drive requires an assessment and
        # the student has one on file, include its 10% component so the
        # explanation matches the score actually used for screening.
        application = await self.applications.get_existing(drive.id, resume.student_id)
        has_assessment = bool(drive.required_assessment_id)
        assessment_score_pct = (
            application.assessment_score_pct
            if application is not None and getattr(application, "assessment_score_pct", None) is not None
            else None
        )
        breakdown = await self.matching.score_resume_against_drive(
            resume,
            drive,
            company_name,
            assessment_score_pct=assessment_score_pct,
            has_assessment=has_assessment,
        )

        missing_skills = breakdown.get("missing_skills", [])
        chunks = []
        if missing_skills:
            chunks = await self.knowledge_store.retrieve(
                query_skills=missing_skills,
                chunk_types=["job_description", "skill_taxonomy"],
                top_k=5,
            )

        facts = {
            "score_breakdown": {
                "final_score": round(breakdown["final_score"], 3),
                "semantic_score": round(breakdown["semantic_score"], 3),
                "skills_score": round(breakdown["skills_score"], 3),
                "experience_score": round(breakdown["experience_score"], 3),
                # The canonical formula also has a 10% assessment component.
                # Report exactly what was used; full credit means either no
                # assessment is required or none has been recorded yet.
                "assessment_score_pct": assessment_score_pct,
                "assessment_required": has_assessment,
            },
            "matched_skills": breakdown.get("matched_skills", []),
            "missing_skills": missing_skills,
            "retrieved_material": [c.text for c in chunks],
        }

        try:
            narrative = await llm_client.generate_text_async(_SYSTEM_PROMPT, str(facts), thinking=True)
        except LLMUnavailableError:
            logger.warning(
                "LLM unavailable for JD explanation (resume=%s drive=%s) — breakdown only.",
                resume_id, drive_id,
            )
            narrative = None

        return JDExplanationResult(breakdown=breakdown, narrative=narrative)