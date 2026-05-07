from pydantic_ai import Agent
from models.schemas import InterviewPlan
from dotenv import load_dotenv

load_dotenv()

# Define the Resume Parser Agent using the simplified OpenRouter string format
agent = Agent(
    'openrouter:mistralai/mistral-nemo',
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
