from pydantic_ai import Agent
from models.schemas import EvaluationResult
from dotenv import load_dotenv

# backend/.env must be loaded before utils.config resolves model constants at
# import time. Local `uv run` processes depend on it; Docker/compose and test
# envs are set before process start and win either way (load_dotenv never
# overrides existing vars).
load_dotenv()

from utils.config import EVALUATOR_MODEL  # noqa: E402  (must follow load_dotenv)

# Define the Answer Evaluator Agent. Model selectable via EVALUATOR_MODEL /
# REASONING_MODEL (see utils/config.py).
evaluator_agent = Agent(
    EVALUATOR_MODEL,
    output_type=EvaluationResult,
    system_prompt=(
        "You are an expert technical interviewer evaluating a candidate's answer. "
        "You will be provided with the candidate's answer to an interview question, "
        "as well as the context of what skills you are looking for. "
        "Your task is to analyze their answer and provide an evaluation. "
        "1. Score the answer as 'Poor', 'Fair', 'Good', or 'Excellent'. "
        "2. Provide brief, constructive feedback on the answer. "
        "3. Optionally, suggest a follow-up question to probe deeper into their answer or address any gaps."
    )
)
