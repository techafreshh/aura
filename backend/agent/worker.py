import logging
import httpx
import sys
import os
from pathlib import Path

# Add the backend directory to sys.path to allow running as a script
backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.append(str(backend_root))

from dataclasses import dataclass
from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    voice,
    inference,
    llm,
)
from livekit.plugins import silero
from models.schemas import InterviewPlan
from agent.evaluator import evaluator_agent
from agent.reporter import reporter_agent

load_dotenv()

logger = logging.getLogger("voice-agent")
logger.setLevel(logging.INFO)

@dataclass
class InterviewContext:
    plan: InterviewPlan
    current_phase: str = "Intro"

class InterviewWorkflow:
    def __init__(self, plan: InterviewPlan, session: voice.AgentSession, session_id: str):
        self.context = InterviewContext(plan=plan)
        self.session = session
        self.session_id = session_id

    @llm.function_tool(description="Evaluate the candidate's answer and suggest a follow-up question.")
    async def evaluate_answer(self, response_summary: str) -> str:
        logger.info(f"Evaluating answer: {response_summary}")
        # Build prompt context for the evaluator
        prompt = f"Skills to look for: {self.context.plan.extracted_skills}\nCandidate's Answer: {response_summary}"
        result = await evaluator_agent.run(prompt)
        eval_result = result.output
        return f"Score: {eval_result.score}. Feedback: {eval_result.feedback}. Follow-up: {eval_result.suggested_follow_up}"

    @llm.function_tool(description="End the interview and generate a final report.")
    async def end_interview(self) -> str:
        logger.info("Ending interview and generating report...")
        # Note: in a real application, you would pass the full transcript to the reporter
        transcript = "Mock transcript of the interview."
        result = await reporter_agent.run(f"Candidate Name: {self.context.plan.candidate_name}\nTranscript: {transcript}")
        report = result.output
        logger.info(f"Report generated with score: {report.overall_score}")

        # Post the report to the backend
        backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{backend_url}/report/{self.session_id}",
                    json=report.model_dump()
                )
                if response.status_code == 200:
                    logger.info("Successfully saved report to backend.")
                else:
                    logger.error(f"Failed to save report: {response.text}")
        except Exception as e:
            logger.error(f"Error saving report: {e}")

        self.context.current_phase = "Outro"
        return f"The interview is over. The final report has been generated with a score of {report.overall_score}."

async def entrypoint(ctx: JobContext):
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    
    session_id = ctx.room.name
    
    # Use the same port the user is running on if possible, otherwise default to 8000
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    
    # Fetch plan from backend
    plan = None
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Fetching plan from {backend_url}/plan/{session_id}")
            response = await client.get(f"{backend_url}/plan/{session_id}")
            if response.status_code == 200:
                plan_data = response.json()
                plan = InterviewPlan(**plan_data)
                logger.info(f"Successfully fetched plan for candidate: {plan.candidate_name}")
            else:
                logger.warning(f"Failed to fetch plan (Status {response.status_code}): {response.text}")
    except Exception as e:
        logger.error(f"Error fetching plan from {backend_url}: {e}")

    # Fallback plan if fetch fails
    if not plan:
        logger.info("Using fallback interview plan.")
        plan = InterviewPlan(candidate_name="Candidate", extracted_skills=[], question_bank=[])

    # Initialize the AgentSession with LiveKit's managed inference models.
    session = voice.AgentSession(
        vad=silero.VAD.load(),
        stt=inference.STT(model="deepgram/nova-2"),
        llm=inference.LLM(model="openai/gpt-4o-mini"),
        tts=inference.TTS(model="cartesia/sonic"),
    )
    
    workflow = InterviewWorkflow(plan=plan, session=session, session_id=session_id)

    # Initial instructions combining base instructions and the dynamic plan
    instructions = (
        f"You are a friendly and professional AI Interviewer. "
        f"You are interviewing {plan.candidate_name}. "
        f"Their skills include: {', '.join(plan.extracted_skills)}. "
        f"Here are some questions you can ask: {', '.join(plan.question_bank)}. "
        "Your goal is to conduct a smooth, conversational interview. "
        "Start by greeting the candidate. "
        "Use the evaluate_answer tool to score their responses and get follow-up suggestions. "
        "When the interview is complete, use the end_interview tool. "
        "Keep your responses concise and wait for the candidate to finish speaking before responding."
    )

    # Define the Agent with instructions and tools
    agent = voice.Agent(
        instructions=instructions,
        tools=llm.find_function_tools(workflow)
    )

    # Start the session with the agent
    await session.start(agent, room=ctx.room)
    
    # Greet the candidate
    session.say(f"Hello {plan.candidate_name}! I am your AI interviewer today. How are you doing?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
