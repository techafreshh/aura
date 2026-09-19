from pydantic_ai import Agent
from models.schemas import ParsedResumeProfile
from dotenv import load_dotenv

# backend/.env must be loaded before utils.config resolves model constants at
# import time. Local `uv run` processes depend on it; Docker/compose and test
# envs are set before process start and win either way (load_dotenv never
# overrides existing vars).
load_dotenv()

from utils.config import PROFILE_MODEL  # noqa: E402  (must follow load_dotenv)

# Define the Profile Parser Agent: extracts job-board profile fields from a
# resume's text. Model selectable via PROFILE_MODEL / REASONING_MODEL (see
# utils/config.py).
agent = Agent(
    PROFILE_MODEL,
    output_type=ParsedResumeProfile,
    system_prompt=(
        "You are an expert technical recruiter who builds candidate profiles from resumes. "
        "You will receive the plain text of a resume. Extract structured profile fields: "
        "1. headline: a short professional headline (e.g. 'Senior Backend Engineer | Python, Go'). "
        "2. location: city/region if present. "
        "3. summary: a 2-4 sentence professional summary written in third person. "
        "4. skills: the candidate's core technical and professional skills (max 30). "
        "5. experience: positions held, most recent first (title, company, start, end, description). "
        "6. education: schools/programs (school, degree, field, start, end). "
        "7. linkedin_url / github_url / portfolio_url when present in the text. "
        "Use null for fields you cannot find — never invent facts. "
        "Do not include the question bank or interview questions; this is a profile, not an interview plan."
    )
)
