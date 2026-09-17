from pydantic_ai import Agent
from models.schemas import FinalReport
from dotenv import load_dotenv

# backend/.env must be loaded before utils.config resolves model constants at
# import time. Local `uv run` processes depend on it; Docker/compose and test
# envs are set before process start and win either way (load_dotenv never
# overrides existing vars).
load_dotenv()

from utils.config import REPORTER_MODEL  # noqa: E402  (must follow load_dotenv)

# Define the Report Generator Agent. Model selectable via REPORTER_MODEL /
# REASONING_MODEL (see utils/config.py).
reporter_agent = Agent(
    REPORTER_MODEL,
    output_type=FinalReport,
    system_prompt=(
        "You are a senior technical recruiter responsible for summarizing an interview. "
        "You will be provided with a complete transcript of an interview, including the "
        "questions asked, the candidate's answers, and intermediate evaluations. "
        "Your task is to generate a comprehensive, structured final report. "
        "1. Extract the candidate's name from the context. "
        "2. Assign an overall score from 1-100 based on their performance. "
        "3. Break down the performance into relevant section grades (e.g., 'Technical', 'Behavioral'). "
        "4. Identify the candidate's key strengths and weaknesses. "
        "5. Provide a final hiring recommendation ('Hire', 'No Hire', 'Strong Hire', or 'Hold'). "
        "6. Write a comprehensive summary paragraph of the interview."
    )
)
