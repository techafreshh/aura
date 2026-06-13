import logging
import asyncio
import httpx
import sys
import os
import time
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
from livekit.agents.telemetry import set_tracer_provider
from livekit.plugins import silero
from models.schemas import InterviewPlan, FinalReport
from agent.evaluator import evaluator_agent
from agent.reporter import reporter_agent
from utils.tracing import setup_langfuse

load_dotenv()

import sentry_sdk

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=1.0,
    environment=os.getenv("ENVIRONMENT", "production"),
)

logger = logging.getLogger("voice-agent")
logger.setLevel(logging.INFO)

# Initialize Langfuse at module level so Agent.instrument_all() patches agents before any room connects
_langfuse_provider = setup_langfuse()

@dataclass
class InterviewContext:
    plan: InterviewPlan
    current_phase: str = "Intro"
    transcript: list = field(default_factory=list)
    start_time: float = 0.0
    report_generated: bool = False


async def generate_and_save_report(context: InterviewContext, session_id: str):
    """Generate report from transcript and POST it to the backend."""
    if context.report_generated:
        return
    context.report_generated = True

    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    transcript_text = "\n".join(f"{e['speaker']}: {e['text']}" for e in context.transcript) if context.transcript else "No transcript available."
    logger.info(f"Generating report from transcript ({len(context.transcript)} entries)")

    try:
        result = await reporter_agent.run(
            f"Candidate: {context.plan.candidate_name}\n"
            f"Skills: {', '.join(context.plan.extracted_skills)}\n"
            f"Transcript:\n{transcript_text}"
        )
        report = result.output
    except Exception as e:
        logger.error(f"Report generation failed for {session_id}: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)
        report = FinalReport(
            candidate_name=context.plan.candidate_name,
            overall_score=0,
            section_grades=[],
            strengths=[],
            weaknesses=["Report generation encountered an error."],
            recommendation="Hold",
            summary="An error occurred during report generation. Please review the transcript manually."
        )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{backend_url}/report/{session_id}",
                json=report.model_dump()
            )
            if resp.status_code != 200:
                logger.error(f"Report save failed: {resp.status_code} {resp.text}")
                sentry_sdk.capture_message(f"Report save failed: {resp.status_code}")
            else:
                logger.info("Successfully saved report to backend.")
    except Exception as e:
        logger.error(f"HTTP error saving report for {session_id}: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{backend_url}/transcript/{session_id}",
                json={"candidate_name": context.plan.candidate_name, "entries": context.transcript}
            )
    except Exception as e:
        logger.error(f"Transcript save failed for {session_id}: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)


class InterviewWorkflow:
    def __init__(self, plan: InterviewPlan, session: voice.AgentSession, session_id: str):
        self.context = InterviewContext(plan=plan)
        self.session = session
        self.session_id = session_id

    @llm.function_tool(description=(
        "Evaluate the candidate's last answer. Pass the candidate's EXACT words as 'candidate_response'. "
        "Do NOT summarize or paraphrase. Only call when you need help deciding what to ask next."
    ))
    async def evaluate_answer(self, candidate_response: str) -> str:
        logger.info(f"Evaluating answer: {candidate_response}")
        prompt = (
            f"Skills to look for: {self.context.plan.extracted_skills}\n"
            f"Candidate's Exact Response: {candidate_response}"
        )
        try:
            eval_result = await evaluator_agent.run(prompt)
            if eval_result.output.suggested_follow_up:
                return f"Ask this follow-up: {eval_result.output.suggested_follow_up}"
        except Exception as e:
            logger.warning(f"Evaluation failed: {e}")
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

    # Use module-level Langfuse provider for LiveKit telemetry
    if _langfuse_provider:
        set_tracer_provider(_langfuse_provider, metadata={"langfuse.session.id": session_id})
    
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
    workflow.context.start_time = time.time()

    # Collect transcript via events
    @session.on("user_input_transcribed")
    def on_user_input(ev):
        if ev.is_final:
            workflow.context.transcript.append({"speaker": "Candidate", "text": ev.transcript, "timestamp_s": round(time.time() - workflow.context.start_time, 2)})

    @session.on("conversation_item_added")
    def on_conversation_item(ev):
        item = ev.item
        if hasattr(item, 'role') and item.role == 'assistant':
            text_parts = []
            if hasattr(item, 'content'):
                for part in item.content:
                    if hasattr(part, 'text') and part.text:
                        text_parts.append(part.text)
            if text_parts:
                workflow.context.transcript.append({"speaker": "Interviewer", "text": " ".join(text_parts), "timestamp_s": round(time.time() - workflow.context.start_time, 2)})

    # Generate report immediately when participant disconnects, then shut down the worker
    report_task = None

    @ctx.room.on("participant_disconnected")
    def on_participant_left(participant):
        nonlocal report_task
        logger.info(f"Participant {participant.identity} disconnected. Triggering report generation and shutdown...")

        async def _finalize():
            try:
                await generate_and_save_report(workflow.context, session_id)
            finally:
                logger.info("Shutting down agent session to release resources.")
                ctx.shutdown(reason="participant_disconnected")

        report_task = asyncio.ensure_future(_finalize())

    # Also generate on shutdown as safety net
    async def on_shutdown():
        if report_task:
            try:
                await report_task
            except Exception as e:
                logger.error(f"Report task errored: {e}")
        else:
            await generate_and_save_report(workflow.context, session_id)
        if _langfuse_provider:
            _langfuse_provider.force_flush()

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
