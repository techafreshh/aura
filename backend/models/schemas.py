from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime
import json

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

class TranscriptEntry(BaseModel):
    speaker: str
    text: str
    timestamp_s: float

class TranscriptPayload(BaseModel):
    candidate_name: str
    entries: List[TranscriptEntry]


class SessionSummary(BaseModel):
    session_id: str
    candidate_name: str
    overall_score: Optional[int] = None
    recommendation: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None

    @classmethod
    def from_db(cls, session) -> "SessionSummary":
        duration = None
        if session.completed_at and session.created_at:
            duration = int((session.completed_at - session.created_at).total_seconds())
        return cls(
            session_id=session.id,
            candidate_name=session.candidate_name,
            overall_score=_extract_score(session.report_json),
            recommendation=_extract_recommendation(session.report_json),
            status=session.status,
            created_at=session.created_at,
            completed_at=session.completed_at,
            duration_seconds=duration,
        )


def _extract_score(report_json: Optional[str]) -> Optional[int]:
    if not report_json:
        return None
    try:
        return json.loads(report_json).get("overall_score")
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_recommendation(report_json: Optional[str]) -> Optional[str]:
    if not report_json:
        return None
    try:
        return json.loads(report_json).get("recommendation")
    except (json.JSONDecodeError, TypeError):
        return None
