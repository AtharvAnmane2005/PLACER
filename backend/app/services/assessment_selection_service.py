"""Deterministic, rule-driven question selection shared by templates and
standardized placement assessments.

The selector never creates questions. It only picks real, active questions
from MongoDB and reports precise deficits when the bank is insufficient.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.assessment import DifficultyLevel, QuestionInDB, QuestionStatus, QuestionType
from app.repositories.question_repository import QuestionRepository


@dataclass
class SectionSelection:
    name: str
    question_ids: list[str] = field(default_factory=list)
    difficulties: list[str] = field(default_factory=list)
    deficits: list[str] = field(default_factory=list)


@dataclass
class SelectionResult:
    questions: list[QuestionInDB]
    sections: list[SectionSelection]
    deficits: list[str]


def allocate_difficulty_slots(section_sizes: list[int], distribution: dict[str, int]) -> list[list[DifficultyLevel]]:
    """Spread the global difficulty quota across sections, balanced by round.

    For five sections of four with a 6/10/4 quota this yields two easy and two
    medium in the first section and one easy, two medium and one hard in each
    of the others — every section has exactly four questions and the totals
    are exactly 6/10/4.
    """
    total = sum(section_sizes)
    slots: list[DifficultyLevel] = []
    for difficulty in (DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD):
        slots.extend([difficulty] * max(0, int(distribution.get(difficulty.value, 0))))
    if len(slots) < total:
        slots.extend([DifficultyLevel.MEDIUM] * (total - len(slots)))
    slots = slots[:total]

    allocated: list[list[DifficultyLevel]] = [[] for _ in section_sizes]
    index = 0
    while index < len(slots):
        progressed = False
        for section_index, size in enumerate(section_sizes):
            if index >= len(slots):
                break
            if len(allocated[section_index]) < size:
                allocated[section_index].append(slots[index])
                index += 1
                progressed = True
        if not progressed:
            break
    return allocated


class QuestionSelector:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.questions = QuestionRepository(db)

    async def _eligible(
        self,
        *,
        category_ids: list[str],
        difficulty: DifficultyLevel,
        question_types: list[QuestionType],
        topics: list[str],
        skills: list[str],
        seed: int | None = None,
    ) -> list[QuestionInDB]:
        query: dict = {
            "difficulty": difficulty.value,
            "status": {"$in": [QuestionStatus.ACTIVE.value, None]},
        }
        if category_ids:
            query["category_id"] = {"$in": category_ids}
        if question_types:
            query["type"] = {"$in": [t.value for t in question_types]}
        candidates = await self.questions.find_many(query, limit=2000)

        def relevant(question: QuestionInDB) -> bool:
            if topics:
                haystack = {str(question.topic or "").lower(), *(t.lower() for t in question.skill_tags)}
                if not any(topic.lower() in haystack or topic.lower() in str(question.topic or "").lower() for topic in topics):
                    return False
            if skills:
                skill_values = {str(question.skill or "").lower(), *(s.lower() for s in question.skill_tags)}
                if not any(skill.lower() in skill_values for skill in skills):
                    return False
            return True

        candidates = [q for q in candidates if relevant(q)]
        if seed is None:
            return sorted(candidates, key=lambda q: (q.created_at.isoformat(), q.id))
        # Seeded selection keeps production behaviour unchanged (no seed =
        # stable chronological order) while letting bulk seeders create
        # varied, reproducible question sets for different drives.
        return sorted(
            candidates,
            key=lambda q: hashlib.sha256(f"{seed}:{q.id}".encode("utf-8")).hexdigest(),
        )

    async def select(
        self,
        *,
        sections: list[dict],
        distribution: dict[str, int],
        question_types: list[QuestionType] | None = None,
        topics: list[str] | None = None,
        skills: list[str] | None = None,
        seed: int | None = None,
    ) -> SelectionResult:
        sizes = [int(section.get("questions", 0)) for section in sections]
        slots_by_section = allocate_difficulty_slots(sizes, distribution)
        selected: list[QuestionInDB] = []
        section_results: list[SectionSelection] = []
        deficits: list[str] = []
        used_ids: set[str] = set()

        for section, slots in zip(sections, slots_by_section):
            name = str(section.get("name", "Section"))
            result = SectionSelection(name=name)

            # Per-section coding quota. Standardized placement assessments ask
            # for one coding question in the Programming section; practice and
            # template assessments may ask for more. The quota is satisfied
            # from the hardest planned slots first so a coding item carries a
            # meaningful share of the marks.
            #
            # The quota is a *preference*, not a hard requirement: a question
            # bank without coding questions must still be able to generate an
            # assessment. Any reserved slot that cannot be filled with a coding
            # question is released back to the objective pool.
            coding_needed = max(0, int(section.get("coding_questions", 0) or 0))
            coding_needed = min(coding_needed, len(slots))
            remaining_slots = list(slots)
            coding_slots: list[DifficultyLevel] = []
            for difficulty in (DifficultyLevel.HARD, DifficultyLevel.MEDIUM, DifficultyLevel.EASY):
                while len(coding_slots) < coding_needed and difficulty in remaining_slots:
                    remaining_slots.remove(difficulty)
                    coding_slots.append(difficulty)

            objective_types = [t for t in (question_types or []) if t != QuestionType.CODING]
            if coding_needed and not objective_types:
                objective_types = [
                    QuestionType.MCQ,
                    QuestionType.MULTIPLE_SELECT,
                    QuestionType.TRUE_FALSE,
                ]

            pools: dict[tuple[str, DifficultyLevel], list[QuestionInDB]] = {}

            # Fill the coding slots first so released slots can be handed to
            # the objective pool below.
            for difficulty in (DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD):
                needed = coding_slots.count(difficulty)
                if needed == 0:
                    continue
                available = await self._eligible(
                    category_ids=[str(c) for c in section.get("category_ids", [])],
                    difficulty=difficulty,
                    question_types=[QuestionType.CODING],
                    topics=topics or [],
                    skills=[str(s) for s in section.get("skill_tags", [])] + (skills or []),
                    seed=seed,
                )
                fresh = [q for q in available if q.id not in used_ids][:needed]
                pools[("coding", difficulty)] = fresh
                used_ids.update(q.id for q in fresh)
                if len(fresh) < needed:
                    release = needed - len(fresh)
                    remaining_slots.extend([difficulty] * release)
                    kept: list[DifficultyLevel] = []
                    dropped = 0
                    for slot in coding_slots:
                        if slot == difficulty and dropped < release:
                            dropped += 1
                            continue
                        kept.append(slot)
                    coding_slots = kept

            for difficulty in (DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD):
                needed = remaining_slots.count(difficulty)
                if needed == 0:
                    continue
                available = await self._eligible(
                    category_ids=[str(c) for c in section.get("category_ids", [])],
                    difficulty=difficulty,
                    question_types=objective_types,
                    topics=topics or [],
                    skills=[str(s) for s in section.get("skill_tags", [])] + (skills or []),
                    seed=seed,
                )
                fresh = [q for q in available if q.id not in used_ids][:needed]
                if len(fresh) < needed:
                    message = (
                        f"{name} / {difficulty.value} (objective): need {needed} "
                        f"eligible question(s), found {len(fresh)}."
                    )
                    result.deficits.append(message)
                    deficits.append(message)
                pools[("objective", difficulty)] = fresh
                used_ids.update(q.id for q in fresh)

            # Preserve the planned difficulty order for this section, choosing
            # a coding pool exactly on the slots reserved for coding.
            coding_left = {d: coding_slots.count(d) for d in DifficultyLevel}
            taken: dict[tuple[str, DifficultyLevel], int] = {key: 0 for key in pools}
            for difficulty in slots:
                if coding_left.get(difficulty, 0) > 0:
                    kind = "coding"
                    coding_left[difficulty] -= 1
                else:
                    kind = "objective"
                pool = pools.get((kind, difficulty), [])
                position = taken.get((kind, difficulty), 0)
                if position < len(pool):
                    question = pool[position]
                    taken[(kind, difficulty)] = position + 1
                    result.question_ids.append(question.id)
                    result.difficulties.append(difficulty.value)
                    selected.append(question)
            section_results.append(result)

        return SelectionResult(questions=selected, sections=section_results, deficits=deficits)
