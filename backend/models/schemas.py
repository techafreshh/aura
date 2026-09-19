from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional
from datetime import datetime
import json
import re

class InterviewPlan(BaseModel):
    candidate_name: str = Field(description="The name of the candidate extracted from the resume.")
    extracted_skills: List[str] = Field(description="A list of core skills identified from the resume.")
    question_bank: List[str] = Field(description="A list of 3-5 personalized interview questions.")
    job_description: Optional[str] = Field(
        default=None,
        description="Optional job description the interview questions were tailored to.",
    )

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


class AdminSessionDetail(BaseModel):
    """Full session detail for admin view, including plan, report, and transcript."""

    session_id: str
    candidate_name: str
    user_email: str
    user_id: str
    plan: Optional[InterviewPlan] = None
    report: Optional[FinalReport] = None
    transcript: Optional[list] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class SessionSummary(BaseModel):
    """Lightweight session summary for list views (admin dashboard and user history).

    Note: `overall_score` and `recommendation` are extracted from the stored
    report JSON blob, and `duration_seconds` is computed from timestamps.
    """

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
        """Build a summary from a database InterviewSession row.

        Extracts score/recommendation from report_json and computes duration.
        """
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
    """Extract overall_score from a stored report JSON string.

    Returns None if the input is empty, None, or contains invalid JSON.
    """
    if not report_json:
        return None
    try:
        return json.loads(report_json).get("overall_score")
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_recommendation(report_json: Optional[str]) -> Optional[str]:
    """Extract recommendation from a stored report JSON string.

    Returns None if the input is empty, None, or contains invalid JSON.
    """
    if not report_json:
        return None
    try:
        return json.loads(report_json).get("recommendation")
    except (json.JSONDecodeError, TypeError):
        return None


class InviteCreate(BaseModel):
    """Payload for a recruiter creating an interview invite with custom questions."""

    title: str = Field(min_length=1, max_length=200, description="Name of the role/position being interviewed for.")
    context: Optional[str] = Field(
        default=None,
        max_length=4000,
        description="Optional job description or context shared with the AI interviewer.",
    )
    questions: List[str] = Field(
        min_length=2,
        max_length=5,
        description="The questions the AI interviewer must ask (2-5 to bound interview cost).",
    )

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str) -> str:
        """Strip and reject whitespace-only titles.

        ``min_length=1`` alone accepts ``"   "``, which the endpoint then strips
        to an empty title and stores in a non-nullable column.
        """
        value = value.strip()
        if not value:
            raise ValueError("Title must not be empty.")
        return value

    @field_validator("questions")
    @classmethod
    def _clean_questions(cls, value: List[str]) -> List[str]:
        cleaned = []
        for q in value:
            if not isinstance(q, str):
                raise ValueError("Each question must be a string.")
            q = q.strip()
            if not q:
                raise ValueError("Questions must not be empty.")
            if len(q) > 500:
                raise ValueError("Each question must be 500 characters or fewer.")
            cleaned.append(q)
        return cleaned


class InviteOut(BaseModel):
    """Invite row as returned in recruiter list/detail views."""

    invite_id: str
    title: str
    context: Optional[str] = None
    questions: List[str]
    token: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    candidate_user_id: Optional[str] = None
    session_id: Optional[str] = None
    # Fields joined from the linked interview session, if any
    candidate_name: Optional[str] = None
    overall_score: Optional[int] = None
    recommendation: Optional[str] = None


class RecruiterInvitesResponse(BaseModel):
    invites: List[InviteOut]
    quota_used: int
    quota_limit: int


class InviteDetail(InviteOut):
    """Full recruiter-facing invite detail including report and transcript."""

    report: Optional[FinalReport] = None
    transcript: Optional[list] = None


class InvitePreview(BaseModel):
    """What a candidate sees before starting an invited interview."""

    title: str
    context: Optional[str] = None
    questions: List[str]
    recruiter_name: str
    # Company branding from the recruiter's profile, when set
    recruiter_company: Optional[str] = None


class InviteStartResponse(BaseModel):
    """Result of redeeming an invite: a session ready for the normal token flow."""

    session_id: str
    plan: InterviewPlan


# --- Candidate / recruiter profiles ------------------------------------------


class ExperienceEntry(BaseModel):
    """One position on the candidate profile, job-board style."""

    title: str = Field(min_length=1, max_length=120, description="Job title.")
    company: str = Field(min_length=1, max_length=120, description="Company or employer.")
    start: str = Field(default="", max_length=40, description="e.g. '2022-03' or 'Spring 2022'.")
    end: str = Field(default="", max_length=40, description="Empty or 'Present' for current roles.")
    description: str = Field(default="", max_length=2000)

    @field_validator("title", "company")
    @classmethod
    def _clean_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Title and company must not be empty.")
        return value

    @field_validator("start", "end", "description")
    @classmethod
    def _clean_free(cls, value: str) -> str:
        return value.strip()


class EducationEntry(BaseModel):
    """One school/program on the candidate profile."""

    school: str = Field(min_length=1, max_length=160)
    degree: str = Field(default="", max_length=160)
    field: str = Field(default="", max_length=160)
    start: str = Field(default="", max_length=40)
    end: str = Field(default="", max_length=40)

    @field_validator("school")
    @classmethod
    def _clean_school(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("School must not be empty.")
        return value

    @field_validator("degree", "field", "start", "end")
    @classmethod
    def _clean_free(cls, value: str) -> str:
        return value.strip()


def _clean_str_list(max_items: int, max_len: int, what: str):
    """Validator factory for string-list fields (skills)."""

    def _validate(value: List[str]) -> List[str]:
        cleaned = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"Each {what} entry must be a string.")
            item = item.strip()
            if not item:
                continue
            if len(item) > max_len:
                raise ValueError(f"Each {what} entry must be {max_len} characters or fewer.")
            cleaned.append(item)
        if len(cleaned) > max_items:
            raise ValueError(f"At most {max_items} {what} allowed.")
        return cleaned

    return _validate


def _clean_entry_list(model_cls, max_items: int, what: str):
    """Validator factory for entry-list fields (experience, education)."""

    def _validate(value) -> list:
        if len(value) > max_items:
            raise ValueError(f"At most {max_items} {what} allowed.")
        return list(value)

    return _validate


class CandidateProfileIn(BaseModel):
    """Updatable candidate profile fields (PUT /profile/candidate body)."""

    headline: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=4000)
    skills: List[str] = Field(default_factory=list, max_length=30)
    experience: List[ExperienceEntry] = Field(default_factory=list, max_length=15)
    education: List[EducationEntry] = Field(default_factory=list, max_length=15)
    linkedin_url: Optional[str] = Field(default=None, max_length=512)
    github_url: Optional[str] = Field(default=None, max_length=512)
    portfolio_url: Optional[str] = Field(default=None, max_length=512)

    @field_validator("headline", "location", "summary")
    @classmethod
    def _clean_free_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("skills")
    @classmethod
    def _clean_skills(cls, value: List[str]) -> List[str]:
        return _clean_str_list(30, 60, "skills")(value)

    @field_validator("experience")
    @classmethod
    def _clean_experience(cls, value: List[ExperienceEntry]) -> List[ExperienceEntry]:
        return _clean_entry_list(ExperienceEntry, 15, "experience entries")(value)

    @field_validator("education")
    @classmethod
    def _clean_education(cls, value: List[EducationEntry]) -> List[EducationEntry]:
        return _clean_entry_list(EducationEntry, 15, "education entries")(value)

    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def _clean_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not re.match(r"^https?://", value, flags=re.IGNORECASE):
            raise ValueError("Links must start with http:// or https://")
        return value[:512]


class CandidateProfileOut(BaseModel):
    """Candidate profile as returned by GET /profile/candidate."""

    headline: str = ""
    location: str = ""
    summary: str = ""
    skills: List[str] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    resume_stored: bool = False
    resume_uploaded_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> "CandidateProfileOut":
        """Build from a CandidateProfile ORM row (JSON columns parsed here)."""

        def _load(name: str) -> list:
            raw = getattr(row, name, None)
            if not raw:
                return []
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []

        return cls(
            headline=row.headline,
            location=row.location,
            summary=row.summary,
            skills=_load("skills_json"),
            experience=[ExperienceEntry.model_validate(e) for e in _load("experience_json") if isinstance(e, dict)],
            education=[EducationEntry.model_validate(e) for e in _load("education_json") if isinstance(e, dict)],
            linkedin_url=row.linkedin_url,
            github_url=row.github_url,
            portfolio_url=row.portfolio_url,
            resume_stored=row.resume_stored,
            resume_uploaded_at=row.resume_uploaded_at,
        )


class RecruiterProfileIn(BaseModel):
    """Updatable recruiter profile fields (PUT /profile/recruiter body)."""

    company_name: str = Field(default="", max_length=200)
    job_title: str = Field(default="", max_length=120)
    company_website: Optional[str] = Field(default=None, max_length=512)
    company_location: str = Field(default="", max_length=120)

    @field_validator("company_name", "job_title", "company_location")
    @classmethod
    def _clean_free_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("company_website")
    @classmethod
    def _clean_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not re.match(r"^https?://", value, flags=re.IGNORECASE):
            raise ValueError("The website must start with http:// or https://")
        return value[:512]


class RecruiterProfileOut(BaseModel):
    """Recruiter profile as returned by GET /profile/recruiter."""

    company_name: str = ""
    job_title: str = ""
    company_website: Optional[str] = None
    company_location: str = ""


class ParsedResumeProfile(BaseModel):
    """Structured profile fields extracted from a resume by the profile parser agent.

    Only the fields the model could find are set; the frontend prefills the
    form's empty fields with these and leaves filled fields untouched.
    """

    headline: Optional[str] = Field(default=None, max_length=200)
    location: Optional[str] = Field(default=None, max_length=120)
    summary: Optional[str] = Field(default=None, max_length=4000)
    skills: List[str] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)
    linkedin_url: Optional[str] = Field(default=None, max_length=512)
    github_url: Optional[str] = Field(default=None, max_length=512)
    portfolio_url: Optional[str] = Field(default=None, max_length=512)

    @field_validator("skills")
    @classmethod
    def _clean_skills(cls, value: List[str]) -> List[str]:
        return _clean_str_list(30, 60, "skills")(value)

    @field_validator("experience")
    @classmethod
    def _clean_experience(cls, value: List[ExperienceEntry]) -> List[ExperienceEntry]:
        return _clean_entry_list(ExperienceEntry, 15, "experience entries")(value)

    @field_validator("education")
    @classmethod
    def _clean_education(cls, value: List[EducationEntry]) -> List[EducationEntry]:
        return _clean_entry_list(EducationEntry, 15, "education entries")(value)


class ResumeParseResponse(BaseModel):
    """Result of POST /profile/candidate/resume: parsed fields for review, not saved."""

    parsed: ParsedResumeProfile
    resume_stored: bool = True


class CandidateUserOut(BaseModel):
    """Public-ish identity of a user, joined where a profile references someone."""

    id: str
    name: str
