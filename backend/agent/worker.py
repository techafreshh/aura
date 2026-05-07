import logging
from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    voice,
    inference,
)
from livekit.plugins import silero

load_dotenv()

logger = logging.getLogger("voice-agent")
logger.setLevel(logging.INFO)


async def entrypoint(ctx: JobContext):
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Initialize the AgentSession with LiveKit's managed inference models.
    # These models run through your LiveKit Cloud account and don't require 
    # separate API keys for OpenAI, Deepgram, or Cartesia.
    session = voice.AgentSession(
        vad=silero.VAD.load(),
        stt=inference.STT(model="deepgram/nova-2"),
        llm=inference.LLM(model="openai/gpt-4o-mini"),
        tts=inference.TTS(model="cartesia/sonic"),
    )

    # Define the Agent with instructions
    agent = voice.Agent(
        instructions=(
            "You are a friendly and professional AI Interviewer. "
            "Your goal is to conduct a smooth, conversational interview. "
            "Start by greeting the candidate and explaining that you'll be asking a few questions based on their resume. "
            "Keep your responses concise and wait for the candidate to finish speaking before responding."
        )
    )

    # Start the session with the agent
    await session.start(agent, room=ctx.room)
    
    # Greet the candidate
    session.say("Hello! I am your AI interviewer today. How are you doing?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
