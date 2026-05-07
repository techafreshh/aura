from pydantic import BaseModel, Field
from typing import List

class InterviewPlan(BaseModel):
    candidate_name: str = Field(description="The name of the candidate extracted from the resume.")
    extracted_skills: List[str] = Field(description="A list of core skills identified from the resume.")
    question_bank: List[str] = Field(description="A list of 3-5 personalized interview questions.")

class UploadResponse(BaseModel):
    session_id: str = Field(description="Unique identifier for the interview session.")
    plan_summary: InterviewPlan = Field(description="The generated interview plan based on the resume.")
