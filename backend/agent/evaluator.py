from pydantic_ai import Agent
from models.schemas import EvaluationResult
from dotenv import load_dotenv

load_dotenv()

# Define the Answer Evaluator Agent
evaluator_agent = Agent(
    'openrouter:deepseek/deepseek-v4-flash',
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
