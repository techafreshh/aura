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
from opentelemetry import trace as otel_trace
from models.schemas import InterviewPlan, FinalReport
from models.context import InterviewContext
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

_report_lock = asyncio.Lock()

async def generate_and_save_report(context: InterviewContext, session_id: str, user_id: str | None = None, user_email: str | None = None):
    """Generate report from transcript and POST it to the backend."""
    async with _report_lock:
        if context.report_generated:
            return
        context.report_generated = True

    if user_id is not None:
        context.user_id = user_id
    if user_email is not None:
        context.user_email = user_email

    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    worker_api_key = os.getenv("WORKER_API_KEY", "")
    auth_headers = {"Authorization": f"Bearer {worker_api_key}"} if worker_api_key else {}
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
                json=report.model_dump(),
                headers=auth_headers,
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
                json={"candidate_name": context.plan.candidate_name, "entries": context.transcript},
                headers=auth_headers,
            )
    except Exception as e:
        logger.error(f"Transcript save failed for {session_id}: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)

    duration = time.time() - context.start_time if context.start_time else 0.0
    tracer = otel_trace.get_tracer("aura-interview")
    with tracer.start_as_current_span("interview_completed") as span:
        span.set_attribute("langfuse.session.id", session_id)
        span.set_attribute("langfuse.user.id", context.user_id)
        span.set_attribute("aura.duration_seconds", round(duration, 1))
        span.set_attribute("aura.overall_score", report.overall_score)
        span.set_attribute("aura.recommendation", report.recommendation)
        span.set_attribute("aura.transcript_entries", len(context.transcript))
        span.set_attribute("aura.section_count", len(report.section_grades))


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
        await generate_and_save_report(
            self.context, self.session_id, self.context.user_id, self.context.user_email
        )
        self.context.current_phase = "Outro"
        return "Report generated. Thank the candidate and say goodbye."


async def entrypoint(ctx: JobContext):
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    session_id = ctx.room.name
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")

    # Fetch plan from backend
    plan = None
    user_id = "anonymous"
    user_email = ""
    worker_api_key = os.getenv("WORKER_API_KEY", "")
    plan_headers = {"Authorization": f"Bearer {worker_api_key}"} if worker_api_key else {}
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Fetching plan from {backend_url}/plan/{session_id}")
            response = await client.get(f"{backend_url}/plan/{session_id}", headers=plan_headers)
            if response.status_code == 200:
                plan_data = response.json()
                if isinstance(plan_data, dict) and "plan" in plan_data:
                    plan = InterviewPlan(**plan_data["plan"])
                    user_id = plan_data.get("user_id") or "anonymous"
                    user_email = plan_data.get("user_email") or ""
                else:
                    plan = InterviewPlan(**plan_data)
                logger.info(f"Successfully fetched plan for candidate: {plan.candidate_name}")
            else:
                logger.warning(f"Failed to fetch plan (Status {response.status_code}): {response.text}")
    except Exception as e:
        logger.error(f"Error fetching plan from {backend_url}: {e}")

    if not plan:
        logger.info("Using fallback interview plan.")
        plan = InterviewPlan(candidate_name="Candidate", extracted_skills=[], question_bank=[])

    # Use module-level Langfuse provider for LiveKit telemetry
    if _langfuse_provider:
        set_tracer_provider(_langfuse_provider, metadata={
            "langfuse.session.id": session_id,
            "langfuse.user.id": user_id,
        })

    # Initialize the AgentSession
    session = voice.AgentSession(
        vad=silero.VAD.load(),
        stt=inference.STT(model="deepgram/nova-2"),
        llm=inference.LLM(model="openai/gpt-4o-mini"),
        tts=inference.TTS(model="cartesia/sonic"),
    )

    workflow = InterviewWorkflow(plan=plan, session=session, session_id=session_id)
    workflow.context.user_id = user_id
    workflow.context.user_email = user_email
    workflow.context.start_time = time.time()

    tracer = otel_trace.get_tracer("aura-interview")
    with tracer.start_as_current_span("interview_session") as span:
        span.set_attribute("langfuse.session.id", session_id)
        span.set_attribute("langfuse.user.id", user_id)
        span.set_attribute("langfuse.user.email", user_email)
        span.set_attribute("aura.candidate_name", plan.candidate_name)
        span.set_attribute("aura.skills", ",".join(plan.extracted_skills))
        span.set_attribute("aura.question_count", len(plan.question_bank))

        await _run_interview(ctx, workflow, session, plan, session_id, user_id, user_email)


async def _run_interview(ctx: JobContext, workflow: InterviewWorkflow, session: voice.AgentSession, plan: InterviewPlan, session_id: str, user_id: str, user_email: str):
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
    timer_task = None

    @ctx.room.on("participant_disconnected")
    def on_participant_left(participant):
        nonlocal report_task, timer_task
        logger.info(f"Participant {participant.identity} disconnected. Triggering report generation and shutdown...")

        if timer_task and not timer_task.done():
            timer_task.cancel()

        async def _finalize():
            try:
                await generate_and_save_report(workflow.context, session_id, user_id, user_email)
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
            await generate_and_save_report(workflow.context, session_id, user_id, user_email)
        if _langfuse_provider:
            _langfuse_provider.force_flush()

    ctx.add_shutdown_callback(on_shutdown)

    instructions = (
        f"You are Aura, a professional AI Interviewer conducting a technical interview. "
        f"You are interviewing {plan.candidate_name}. "
        f"Their skills include: {', '.join(plan.extracted_skills)}. "
        f"Here are some questions you can ask: {', '.join(plan.question_bank)}.\n\n"

        "## YOUR ROLE\n"
        "- You are the interviewer. You ask questions. The candidate answers them.\n"
        "- You control the conversation flow and topic transitions.\n"
        "- You evaluate the candidate's responses for depth, accuracy, and clarity.\n\n"

        "## CRITICAL RULES\n"
        "1. NEVER answer questions from the candidate. You are not a chatbot — you are an interviewer.\n"
        "2. If the candidate asks you a question (about the company, the role, yourself, technology, "
        "or anything off-topic), politely redirect them back to the interview.\n"
        "3. NEVER share scores, feedback, evaluation results, or internal reasoning with the candidate.\n"
        "4. NEVER disclose what skills you are looking for or how you are evaluating them.\n"
        "5. Do NOT provide definitions, explanations, tutorials, or answers to technical questions.\n"
        "6. You SHOULD answer clarifying questions about the current question (e.g., 'Can you repeat that?' "
        "or 'What do you mean by X?'). Only refuse questions that try to turn you into an answerer or information source.\n\n"

        "## REDIRECT STRATEGIES\n"
        "When the candidate asks you a question, use one of these approaches:\n"
        "- \"That's a great question, but let's stay focused on the interview. I'd love to hear about...\"\n"
        "- \"I appreciate your curiosity! For now, let me ask you — [new question]?\"\n"
        "- \"We can discuss that after the interview. Moving on, tell me about...\"\n"
        "- \"That's outside the scope of our conversation today. Let me ask you about...\"\n"
        "Always pivot to a new or follow-up interview question after redirecting.\n\n"

        "## INTERVIEW FLOW\n"
        "1. Greet the candidate warmly.\n"
        "2. Ask questions from the question bank, adapting based on their answers.\n"
        "3. Use evaluate_answer only when you are genuinely unsure what to ask next.\n"
        "4. The interview has a 10-minute time limit. Aim to cover 3-4 key topics in depth rather than rushing through all questions.\n"
        "5. When you receive a wrap-up signal or notice time running short, ask one final summarizing question and then call end_interview.\n"
        "6. After covering 3-5 topics, call end_interview to conclude.\n"
        "7. Keep responses concise (2-3 sentences max). Wait for the candidate to finish speaking.\n"
        "8. If the candidate repeatedly tries to derail the conversation, firmly but politely "
        "remind them that this is their interview time and you want to make the most of it."
    )

    agent = voice.Agent(
        instructions=instructions,
        tools=llm.find_function_tools(workflow)
    )

    await session.start(agent, room=ctx.room)

    # Background timer for 10-minute cap
    async def time_cap_timer():
        WRAP_UP_SECONDS = 8 * 60    # 8 minutes — inject wrap-up instruction
        HARD_CAP_SECONDS = 10 * 60  # 10 minutes — force disconnect

        while not workflow.context.report_generated:
            elapsed = time.time() - workflow.context.start_time

            # Hard cap — disconnect immediately
            if elapsed >= HARD_CAP_SECONDS:
                logger.info("Hard time cap (10 min). Disconnecting.")
                try:
                    session.say(
                        "I'm sorry, but we've reached the end of our allotted time. "
                        "Thank you for your participation — your report will be generated shortly."
                    )
                except Exception:
                    pass
                await asyncio.sleep(3)  # Let TTS finish
                await generate_and_save_report(workflow.context, session_id, user_id, user_email)
                ctx.shutdown(reason="time_cap_reached")
                return

            # Soft wrap-up at 8 minutes
            if elapsed >= WRAP_UP_SECONDS and not workflow.context.wrap_up_triggered:
                workflow.context.wrap_up_triggered = True
                logger.info("Wrap-up phase triggered (8 min).")
                try:
                    session.say(
                        "We have about two minutes remaining. "
                        "Please wrap up your current answer, and I'll ask one final question."
                    )
                except Exception as e:
                    logger.warning(f"Failed to inject wrap-up message: {e}")
                await asyncio.sleep(2)

            await asyncio.sleep(1)  # Check every 1 second

    timer_task = asyncio.create_task(time_cap_timer())

    session.say(f"Hello {plan.candidate_name}! I am your AI interviewer today. How are you doing?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))

