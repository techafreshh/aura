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
from models.schemas import InterviewPlan
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

    transcript_text = "\n".join(f"{e['speaker']}: {e['text']}" for e in context.transcript) if context.transcript else "No transcript available."
    logger.info(f"Generating report from transcript ({len(context.transcript)} entries)")

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

            # POST transcript to backend
            await client.post(
                f"{backend_url}/transcript/{session_id}",
                json={"candidate_name": context.plan.candidate_name, "entries": context.transcript},
            )
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

    # Initialize tracing
    trace_provider = setup_langfuse()
    if trace_provider:
        set_tracer_provider(trace_provider, metadata={"langfuse.session.id": session_id})
    
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
        if trace_provider:
            trace_provider.force_flush()

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
