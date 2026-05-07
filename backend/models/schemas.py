from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class InterviewPlan(BaseModel):
    candidate_name: str = Field(description="The name of the candidate extracted from the resume.")
    extracted_skills: List[str] = Field(description="A list of core skills identified from the resume.")
    question_bank: List[str] = Field(description="A list of 3-5 personalized interview questions.")

class UploadResponse(BaseModel):
    session_id: str = Field(description="Unique identifier for the interview session.")
    plan_summary: InterviewPlan = Field(description="The generated interview plan based on the resume.")

class EvaluationResult(BaseModel):
    score: Literal["Poor", "Fair", "Good", "Excellent"] = Field(description="The score for the candidate's answer.")
    feedback: str = Field(description="Brief constructive feedback on the answer.")
    suggested_follow_up: Optional[str] = Field(default=None, description="A suggested follow-up question based on the answer.")

class SectionGrade(BaseModel):
    section_name: str = Field(description="The name of the interview section (e.g., 'Technical', 'Behavioral').")
    score: int = Field(description="Numeric score from 1-10.")
    comments: str = Field(description="Comments and observations for this section.")

class FinalReport(BaseModel):
    candidate_name: str = Field(description="The name of the candidate.")
    overall_score: int = Field(description="Overall numeric score from 1-100.")
    section_grades: List[SectionGrade] = Field(description="Grades for individual sections of the interview.")
    strengths: List[str] = Field(description="Key strengths identified during the interview.")
    weaknesses: List[str] = Field(description="Areas for improvement or weaknesses identified.")
    recommendation: Literal["Hire", "No Hire", "Strong Hire", "Hold"] = Field(description="Final hiring recommendation.")
    summary: str = Field(description="A comprehensive summary of the interview.")
