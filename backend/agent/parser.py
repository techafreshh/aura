from pydantic_ai import Agent
from models.schemas import InterviewPlan
from dotenv import load_dotenv

# backend/.env must be loaded before utils.config resolves model constants at
# import time. Local `uv run` processes depend on it; Docker/compose and test
# envs are set before process start and win either way (load_dotenv never
# overrides existing vars).
load_dotenv()

from utils.config import PARSER_MODEL  # noqa: E402  (must follow load_dotenv)

# Define the Resume Parser Agent. Model selectable via PARSER_MODEL /
# REASONING_MODEL (see utils/config.py).
agent = Agent(
    PARSER_MODEL,
    output_type=InterviewPlan,
    system_prompt=(
        "You are an expert technical recruiter and interviewer. "
        "Your task is to analyze a candidate's resume and extract key information "
        "to prepare for an interview. "
        "1. Extract the candidate's full name. "
        "2. Identify the core technical and professional skills. "
        "3. Formulate 3-5 personalized, high-quality interview questions based on their experience and skills. "
        "The questions should be designed to probe their depth of knowledge and practical experience."
    )
)
