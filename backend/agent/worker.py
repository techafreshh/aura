import logging
import asyncio
import httpx
import sys
import os
from pathlib import Path

# Add the backend directory to sys.path to allow running as a script
backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.append(str(backend_root))

from dataclasses import dataclass, field
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
    transcript_lines: list = field(default_factory=list)
    report_generated: bool = False


async def generate_and_save_report(context: InterviewContext, session_id: str):
    """Generate report from transcript and POST it to the backend."""
    if context.report_generated:
        return
    context.report_generated = True

    transcript_text = "\n".join(context.transcript_lines) if context.transcript_lines else "No transcript available."
    logger.info(f"Generating report from transcript ({len(context.transcript_lines)} lines)")

    try:
        result = await reporter_agent.run(
            f"Candidate Name: {context.plan.candidate_name}\n"
            f"Skills: {', '.join(context.plan.extracted_skills)}\n"
            f"Transcript:\n{transcript_text}"
        )
        report = result.output
        logger.info(f"Report generated with score: {report.overall_score}")

        backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{backend_url}/report/{session_id}",
                json=report.model_dump()
            )
            if response.status_code == 200:
                logger.info("Successfully saved report to backend.")
            else:
                logger.error(f"Failed to save report: {response.text}")
    except Exception as e:
        logger.error(f"Error generating/saving report: {e}")


class InterviewWorkflow:
    def __init__(self, plan: InterviewPlan, session: voice.AgentSession, session_id: str):
        self.context = InterviewContext(plan=plan)
        self.session = session
        self.session_id = session_id

    @llm.function_tool(description="Evaluate the candidate's answer when you're unsure what to ask next or want to change topics. Do NOT call after every answer.")
    async def evaluate_answer(self, response_summary: str) -> str:
        logger.info(f"Evaluating answer: {response_summary}")
        prompt = f"Skills to look for: {self.context.plan.extracted_skills}\nCandidate's Answer: {response_summary}"
        try:
            result = await evaluator_agent.run(prompt)
            eval_result = result.output
            if eval_result.suggested_follow_up:
                return f"Ask this follow-up: {eval_result.suggested_follow_up}"
        except Exception as e:
            logger.warning(f"evaluate_answer failed: {e}")
        return "The answer was satisfactory. Move on to the next topic."

    @llm.function_tool(description="End the interview and generate a final report. Call this when you have asked enough questions.")
    async def end_interview(self) -> str:
        logger.info("Ending interview and generating report...")
        await generate_and_save_report(self.context, self.session_id)
        self.context.current_phase = "Outro"
        return "Report generated. Thank the candidate and say goodbye."


async def entrypoint(ctx: JobContext):
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    
    session_id = ctx.room.name
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

    if not plan:
        logger.info("Using fallback interview plan.")
        plan = InterviewPlan(candidate_name="Candidate", extracted_skills=[], question_bank=[])

    # Initialize the AgentSession
    session = voice.AgentSession(
        vad=silero.VAD.load(),
        stt=inference.STT(model="deepgram/nova-2"),
        llm=inference.LLM(model="openai/gpt-4o-mini"),
        tts=inference.TTS(model="cartesia/sonic"),
    )
    
    workflow = InterviewWorkflow(plan=plan, session=session, session_id=session_id)

    # Collect transcript via events
    @session.on("user_input_transcribed")
    def on_user_input(ev):
        if ev.is_final:
            workflow.context.transcript_lines.append(f"Candidate: {ev.transcript}")

    @session.on("conversation_item_added")
    def on_conversation_item(ev):
        item = ev.item
        if hasattr(item, 'role') and item.role == 'assistant':
            # Extract text content from the ChatMessage
            text_parts = []
            if hasattr(item, 'content'):
                for part in item.content:
                    if hasattr(part, 'text') and part.text:
                        text_parts.append(part.text)
            if text_parts:
                workflow.context.transcript_lines.append(f"Interviewer: {' '.join(text_parts)}")

    # Generate report immediately when participant disconnects
    report_task = None

    @ctx.room.on("participant_disconnected")
    def on_participant_left(participant):
        nonlocal report_task
        logger.info(f"Participant {participant.identity} disconnected. Triggering report generation...")
        report_task = asyncio.ensure_future(generate_and_save_report(workflow.context, session_id))

    # Also generate on shutdown as safety net
    async def on_shutdown():
        if report_task:
            await report_task
        else:
            await generate_and_save_report(workflow.context, session_id)

    ctx.add_shutdown_callback(on_shutdown)

    instructions = (
        f"You are a friendly and professional AI Interviewer. "
        f"You are interviewing {plan.candidate_name}. "
        f"Their skills include: {', '.join(plan.extracted_skills)}. "
        f"Here are some questions you can ask: {', '.join(plan.question_bank)}. "
        "Your goal is to conduct a smooth, conversational interview. "
        "Start by greeting the candidate. "
        "Rely on your own judgment for natural follow-ups — do NOT call evaluate_answer after every response. "
        "Only use evaluate_answer when you're genuinely unsure what to ask next or want to change topics. "
        "IMPORTANT: Never share scores, feedback, or evaluation results with the candidate. "
        "When the interview is complete (after 3-5 questions), use the end_interview tool. "
        "Keep your responses concise and wait for the candidate to finish speaking before responding."
    )

    agent = voice.Agent(
        instructions=instructions,
        tools=llm.find_function_tools(workflow)
    )

    await session.start(agent, room=ctx.room)
    session.say(f"Hello {plan.candidate_name}! I am your AI interviewer today. How are you doing?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
