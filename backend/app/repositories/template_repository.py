from app.models.assessment import AssessmentTemplateInDB
from app.repositories.base import BaseRepository


class AssessmentTemplateRepository(BaseRepository[AssessmentTemplateInDB]):
    collection_name = "assessment_templates"
    model = AssessmentTemplateInDB
