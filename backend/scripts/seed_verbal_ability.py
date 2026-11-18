"""One-off maintenance script: add the missing Verbal Ability category and the
few real questions needed to make standardized placement generation possible.

Run with the backend environment: python seed_verbal_ability.py
Idempotent — skips anything that already exists.
"""
import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from app.models.assessment import CategoryCreateRequest, DifficultyLevel, QuestionCreateRequest, QuestionType
from app.services.placement_assessment_service import PlacementAssessmentService
from app.services.question_service import QuestionService

DB_NAME = "placer_db"

VERBAL_QUESTIONS = [
    {
        "difficulty": DifficultyLevel.EASY,
        "type": QuestionType.MCQ,
        "text": "Choose the word most nearly opposite in meaning to 'BENEVOLENT'.",
        "options": ["Malevolent", "Generous", "Philanthropic", "Kind-hearted"],
        "correct_answer": "Malevolent",
        "topic": "Vocabulary",
        "skill": "Antonyms",
        "explanation": "Benevolent means well-meaning or generous; malevolent means wishing harm, so it is the opposite.",
    },
    {
        "difficulty": DifficultyLevel.MEDIUM,
        "type": QuestionType.MCQ,
        "text": "Select the word that best completes the sentence: 'Despite the committee's early objections, the proposal was ___ adopted by the board.'",
        "options": ["unanimously", "reluctantly", "inadvertently", "barely"],
        "correct_answer": "unanimously",
        "topic": "Grammar",
        "skill": "Fill in the blank",
        "explanation": "'Despite' signals a contrast with the earlier objections, so a word showing full agreement — 'unanimously' — fits best.",
    },
    {
        "difficulty": DifficultyLevel.MEDIUM,
        "type": QuestionType.TRUE_FALSE,
        "text": "In the sentence 'The report that the intern drafted was praised by the manager,' the clause 'that the intern drafted' is a restrictive relative clause.",
        "options": ["True", "False"],
        "correct_answer": "True",
        "topic": "Grammar",
        "skill": "Relative clauses",
        "explanation": "The clause identifies which report is meant and is not set off by commas, so it is a restrictive (defining) relative clause.",
    },
    {
        "difficulty": DifficultyLevel.HARD,
        "type": QuestionType.MCQ,
        "text": "A study found that a new support process cut average handling time by 30%, yet overall customer satisfaction rose only marginally because the quality of issue resolution fell. Which conclusion is best supported by the study?",
        "options": [
            "Faster handling always improves customer satisfaction.",
            "Improvements in speed can be offset by a decline in resolution quality.",
            "Customer satisfaction depends only on how quickly a ticket is closed.",
            "The new process should be abandoned because it increased handling time.",
        ],
        "correct_answer": "Improvements in speed can be offset by a decline in resolution quality.",
        "topic": "Reading Comprehension",
        "skill": "Inference",
        "explanation": "The passage attributes the marginal gain to lower resolution quality, so speed gains alone did not translate into satisfaction.",
    },
]

APTITUDE_QUESTION = {
    "category_id": "Aptitude & Logical Reasoning",
    "difficulty": DifficultyLevel.MEDIUM,
    "type": QuestionType.MCQ,
    "text": "A train 180 metres long crosses a pole in 12 seconds. What is the speed of the train in km/h?",
    "options": ["48 km/h", "54 km/h", "60 km/h", "72 km/h"],
    "correct_answer": "54 km/h",
    "topic": "Speed and Distance",
    "skill": "Quantitative Aptitude",
    "explanation": "Speed = 180 m / 12 s = 15 m/s. Converting to km/h: 15 x 18/5 = 54 km/h.",
}


async def main() -> None:
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client[DB_NAME]
    service = QuestionService(db)

    admin = await db.admins.find_one({})
    if not admin:
        admin = await db["users"].find_one({"role": "admin"})
    if not admin:
        fallback = await db.questions.find_one({})
        admin_user_id = str(fallback["created_by"])
    else:
        admin_user_id = str(admin.get("user_id") or admin.get("_id"))

    category = await service.categories.find_one({"name": {"$regex": "^Verbal Ability$", "$options": "i"}})
    if not category:
        category = await service.create_category(CategoryCreateRequest(name="Verbal Ability"))
        print(f"Created category: {category.name} ({category.id})")
    else:
        print(f"Category already exists: {category.name} ({category.id})")

    created = 0
    for spec in [*VERBAL_QUESTIONS, APTITUDE_QUESTION]:
        payload = QuestionCreateRequest(
            category_id=spec.get("category_id", category.id),
            skill_tags=[spec["topic"], spec["skill"]],
            difficulty=spec["difficulty"],
            type=spec["type"],
            text=spec["text"],
            options=spec["options"],
            correct_answer=spec["correct_answer"],
            topic=spec["topic"],
            skill=spec["skill"],
            explanation=spec["explanation"],
        )
        existing = await service.questions.find_duplicate(payload.text)
        if existing:
            print(f"Skip (already present): {payload.text[:70]}...")
            continue
        question = await service.create_question(admin_user_id, payload)
        created += 1
        print(f"Added {question.difficulty.value}/{question.type.value}: {question.text[:70]}... ({question.id})")
    print(f"\nAdded {created} question(s).")

    drive = await db.placement_drives.find_one({})
    if not drive:
        print("No placement drive exists to check eligibility against.")
    else:
        placement = PlacementAssessmentService(db)
        eligibility = await placement.eligibility(str(drive["_id"]))
        print(f"\nDrive: {drive.get('job_title')} ({drive['_id']})")
        print("Can generate:", eligibility.can_generate)
        for section in eligibility.sections:
            print(f"  {section['name']}: {section['selected']}/{section['questions']}")
        if eligibility.deficits:
            print("Deficits:")
            for deficit in eligibility.deficits:
                print("  -", deficit)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
