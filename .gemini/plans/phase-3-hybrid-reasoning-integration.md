# Feature: phase-3-hybrid-reasoning-integration

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

## Feature Description

Implement Phase 3 of the AI Interviewer project: Hybrid Reasoning Integration. This phase connects the real-time LiveKit voice agent with deep-reasoning Pydantic AI agents to enable context-aware evaluation and structured reporting. It introduces an answer evaluation loop and a final report generation process.

## User Story

As a candidate
I want the AI to understand my specific background and evaluate my answers accurately
So that the interview feels professional and results in a fair assessment.

As a recruiter
I want a structured, data-driven report after the interview
So that I can make an informed hiring decision based on objective criteria.

## Problem Statement

Currently, the LiveKit worker uses a generic system prompt and doesn't utilize the `InterviewPlan` generated from the candidate's resume. It also lacks the ability to score answers or generate a final hiring report. We need to bridge the gap between the low-latency voice pipeline and the structured reasoning capabilities of Pydantic AI.

## Solution Statement

We will integrate Pydantic AI agents as "Tools" within the LiveKit `voice.Agent`. 
1. The FastAPI backend will store the `InterviewPlan` in memory.
2. The LiveKit worker will fetch the plan on startup.
3. An `AnswerEvaluatorAgent` (Pydantic AI) will be exposed as a tool to score responses and suggest follow-ups.
4. A `ReportGeneratorAgent` (Pydantic AI) will process the full transcript at the end to create a `FinalReport`.
5. An `InterviewWorkflow` class will manage phase transitions (Intro -> Behavioral -> Technical -> Outro) and update the agent's instructions dynamically.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**: `backend/agent`, `backend/api`, `backend/models`
**Dependencies**: 
- `pydantic-ai`
- `livekit-agents`
- `httpx` (for internal API calls)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/models/schemas.py` - Why: Needs new models for `EvaluationResult` and `FinalReport`.
- `backend/agent/parser.py` - Why: Pattern for Pydantic AI agents.
- `backend/agent/worker.py` - Why: Main entry point for the voice agent where tools and workflow logic will be added.
- `backend/api/main.py` - Why: Needs to expose the stored `InterviewPlan`.

### New Files to Create

- `backend/agent/evaluator.py` - Pydantic AI agent for scoring candidate answers.
- `backend/agent/reporter.py` - Pydantic AI agent for generating the final JSON report.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LiveKit Agents v1.0 Tools](https://docs.livekit.io/agents/voice-agent/tools/)
  - Why: How to define and use `@llm.function_tool`.
- [Pydantic AI Agents](https://ai.pydantic.dev/agents/)
  - Why: Core logic for evaluation and reporting.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (Data Models & Storage)

Expand the data layer to support evaluation results and final reports. Implement a simple in-memory store in the API to share the `InterviewPlan` between the upload process and the worker.

**Tasks:**
- Add `EvaluationResult`, `SectionGrade`, and `FinalReport` to `backend/models/schemas.py`.
- Update `backend/api/main.py` to store plans in a global dictionary keyed by `session_id`.
- Add `GET /plan/{session_id}` endpoint.

### Phase 2: Reasoning Agents (Pydantic AI)

Create specialized agents for deep reasoning tasks that don't need to be part of the real-time loop.

**Tasks:**
- Implement `AnswerEvaluatorAgent` in `backend/agent/evaluator.py`.
- Implement `ReportGeneratorAgent` in `backend/agent/reporter.py`.

### Phase 3: Workflow & Tools (LiveKit Integration)

Connect the reasoning agents to the LiveKit worker and implement the interview state machine.

**Tasks:**
- Update `backend/agent/worker.py` to fetch the `InterviewPlan` from the backend API on `entrypoint`.
- Implement an `InterviewContext` and `InterviewWorkflow` class in `worker.py` to track state.
- Expose `evaluate_answer` and `end_interview` as LiveKit tools.
- Implement phase transition logic that updates `agent.update_chat_ctx()`.

### Phase 4: Validation

Ensure the end-to-end flow works: Resume Upload -> Plan Generation -> Voice Interview -> Report Generation.

**Tasks:**
- Add unit tests for the new agents.
- Update API tests to verify the plan storage.
- Manual validation of the voice-to-report flow.

---

## STEP-BY-STEP TASKS

### UPDATE `backend/models/schemas.py`
- **ADD**: `EvaluationResult` model.
- **ADD**: `SectionGrade` and `FinalReport` models.
- **VALIDATE**: `uv run ruff check models/schemas.py`

### UPDATE `backend/api/main.py`
- **ADD**: Global `plans: dict[str, InterviewPlan] = {}`.
- **UPDATE**: `upload_resume` to store the generated plan in `plans[session_id]`.
- **CREATE**: `GET /plan/{session_id}` endpoint that returns the plan or 404.
- **VALIDATE**: `uv run pytest tests/test_api.py` (after adding a test case).

### CREATE `backend/agent/evaluator.py`
- **IMPLEMENT**: `evaluator_agent = Agent('openrouter:mistralai/mistral-nemo', result_type=EvaluationResult)`.
- **PROMPT**: System prompt should guide the agent to score an answer based on provided skills and transcript.
- **VALIDATE**: `uv run python -c "from agent.evaluator import evaluator_agent; print('Import OK')"`

### CREATE `backend/agent/reporter.py`
- **IMPLEMENT**: `reporter_agent = Agent('openrouter:mistralai/mistral-nemo', result_type=FinalReport)`.
- **PROMPT**: System prompt should guide the agent to summarize the full interview into a professional report.
- **VALIDATE**: `uv run python -c "from agent.reporter import reporter_agent; print('Import OK')"`

### UPDATE `backend/agent/worker.py`
- **IMPLEMENT**: `InterviewContext` dataclass to hold the `InterviewPlan` and `current_phase`.
- **IMPLEMENT**: `InterviewWorkflow` class with:
    - `__init__(self, plan: InterviewPlan, session: voice.AgentSession)`
    - `@llm.function_tool` `evaluate_answer(self, response_summary: str)`
    - `@llm.function_tool` `end_interview(self)`
- **UPDATE**: `entrypoint` to:
    1. Fetch `session_id` from room name.
    2. Fetch plan from `http://localhost:8000/plan/{session_id}`.
    3. Initialize `InterviewWorkflow`.
    4. Pass `workflow.function_tools()` to the `voice.Agent`.
    5. Inject `InterviewPlan` into the initial `ChatContext`.
- **GOTCHA**: Ensure `httpx` is used for the async API call.
- **VALIDATE**: `uv run python agent/worker.py --help`

---

## TESTING STRATEGY

### Unit Tests
- **Evaluator Agent**: Test with mock transcripts to ensure it returns valid `EvaluationResult`.
- **Reporter Agent**: Test with mock transcripts to ensure it returns valid `FinalReport`.
- **API Store**: Verify that plans are correctly stored and retrieved via `session_id`.

### Integration Tests
- Verify that calling `end_interview` in the worker triggers the reporter agent.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
`cd backend; uv run ruff check .`

### Level 2: Unit Tests
`cd backend; $env:PYTHONPATH="."; uv run pytest`

---

## ACCEPTANCE CRITERIA
- [ ] `InterviewPlan` is successfully shared between API and Worker.
- [ ] `AnswerEvaluatorAgent` can score a response.
- [ ] `ReportGeneratorAgent` can generate a structured JSON report.
- [ ] The LiveKit agent utilizes tools to evaluate and end the session.
- [ ] The interview follows the candidate's specific resume context.

---

## NOTES
- For the MVP, we use an in-memory dictionary for plans. This will be lost if the server restarts, but is sufficient for the current phase.
- We use OpenRouter for the "Reasoning" agents (Evaluator/Reporter) to stay consistent with Phase 1.
