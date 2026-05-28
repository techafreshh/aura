import os
import logging
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger("tracing")

_provider: TracerProvider | None = None


def setup_langfuse() -> TracerProvider | None:
    """Initialize Langfuse as OTel exporter. Returns None if unconfigured. Never raises."""
    global _provider
    if _provider is not None:
        return _provider

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    base_url = os.getenv("LANGFUSE_BASE_URL")

    if not public_key or not secret_key or not base_url:
        logger.info("Langfuse not configured — tracing disabled")
        return None

    try:
        from langfuse import Langfuse
        from pydantic_ai import Agent

        _provider = TracerProvider()

        # Register globally so Pydantic AI's Agent.instrument_all() emits to Langfuse.
        # Must happen before Agent.instrument_all() so the patched agents pick up the global provider.
        otel_trace.set_tracer_provider(_provider)

        Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
            tracer_provider=_provider,
            should_export_span=lambda span: True,
        )

        Agent.instrument_all()
        logger.info("Langfuse tracing initialized (host=%s)", base_url)
        return _provider
    except Exception as e:
        logger.error("Failed to initialize Langfuse: %s", e)
        return None
