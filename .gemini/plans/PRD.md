# AI Interviewer Agent: Product Requirements Document

## 1. Executive Summary
The AI Interviewer Agent is an intelligent, real-time voice application designed to conduct interactive interviews with candidates. By ingesting a user's resume, the agent dynamically formulates personalized questions, evaluates the user's spoken responses in real-time, and probes deeper based on the quality of their answers. 

The core value proposition lies in automating the preliminary interview process while maintaining a conversational, human-like interaction through ultra-low latency voice AI. The MVP goal is to deliver a fully functional end-to-end system where a user can upload a resume, complete a structured voice interview, and generate a final hiring report.

## 2. Mission
To provide a scalable, intelligent, and seamless voice-first interviewing experience that fairly evaluates candidates and streamlines the hiring process for recruiters.

**Core Principles:**
- **Low Latency:** The voice interaction must feel natural, with minimal delay between the candidate speaking and the agent responding.
- **Dynamic Reasoning:** The agent must not follow a rigid script; it should adapt to the candidate's answers and ask meaningful follow-ups.
- **Data-Driven Evaluation:** Feedback and final reports must be structured, objective, and tied to the candidate's resume and rubric.
- **Privacy & Security:** Resume data and audio streams must be handled securely during the session.

## 3. Target Users
- **Primary User:** Job Candidates (Interviewees).
    - **Technical Comfort Level:** Varies. The interface must be intuitive, requiring only basic browser permissions (microphone).
    - **Key Needs:** Clear instructions, visual feedback that the agent is listening/speaking, and a fair evaluation.
- **Secondary User:** Recruiters / Hiring Managers.
    - **Technical Comfort Level:** Moderate. 
    - **Key Needs:** Structured, easy-to-read reports summarizing the candidate's strengths, weaknesses, and a final grade.

## 4. MVP Scope
**Core Functionality:**
- ✅ PDF/Text resume upload and parsing.
- ✅ Real-time two-way voice communication via WebRTC.
- ✅ Dynamic question generation based on parsed resume.
- ✅ Real-time answer evaluation and follow-up generation.
- ✅ Final structured report generation (JSON/Text).
- ❌ Video streaming (audio-only for MVP).
- ❌ Multi-agent panel interviews.

**Technical:**
- ✅ Hybrid Architecture: LiveKit native LLM for real-time voice, Pydantic AI for background reasoning.
- ✅ State machine for interview phases (Intro, Behavioral, Technical, Outro).
- ❌ Persistent database for user accounts and historical reports (transient session state for MVP).

**Integration & Deployment:**
- ✅ FastAPI backend for token generation and file handling.
- ✅ React (Vite) + Shadcn UI frontend.
- ❌ CI/CD pipelines and production Kubernetes deployment.

## 5. User Stories
- **As a candidate**, I want to upload my resume, so that the AI can ask me relevant questions about my specific experience.
- **As a candidate**, I want to see a visualizer indicating when the AI is listening or speaking, so that I know when it's my turn to talk.
- **As a candidate**, I want to read a live text transcript of the conversation, so that I can reference what was just asked or said.
- **As a candidate**, I want the AI to ask follow-up questions if I give a brief answer, so that I can fully demonstrate my knowledge.
- **As a recruiter**, I want the system to generate a final structured JSON report containing grades and insights, so that I can quickly evaluate the candidate's performance.

## 6. Core Architecture & Patterns
**High-Level Architecture:**
- **Hybrid Approach:** 
    - **Real-Time Loop:** LiveKit `VoicePipelineAgent` handles WebRTC, STT (Speech-to-Text), LLM generation, and TTS (Text-to-Speech) for ultra-low latency conversational flow.
    - **Reasoning Loop:** Pydantic AI handles async background tasks (resume parsing, answer evaluation, state transitions, report generation) via tools exposed to the LiveKit agent.
- **Directory Structure (Proposed):**
    ```
    /backend (FastAPI + LiveKit Worker)
      /api (Endpoints for upload, token)
      /agent (LiveKit worker, Pydantic AI tools)
      /models (Pydantic schemas)
    /frontend (React + Vite)
      /src
        /components (Shadcn UI + custom voice UI)
        /hooks (LiveKit state hooks)
    ```

## 7. Tools/Features
**Pydantic AI Agents (Tools):**
- **ResumeParserAgent:** Ingests document text, outputs an `InterviewPlan` struct with extracted skills and a baseline question bank.
- **AnswerEvaluatorAgent:** Ingests the current transcript and rubric, outputs a score and a dynamically generated follow-up question injected into the LiveKit context.
- **ReportGeneratorAgent:** Ingests the full interview transcript, outputs a strongly-typed `FinalReport` (JSON).

**Frontend Core Features:**
- **Pre-Interview Screen:** File dropzone for resume upload, microphone permission request.
- **Active Room UI:**
    - **Audio Visualizer:** Reactive UI component (`AgentAudioVisualizerAura`).
    - **Control Bar:** Mute/unmute, disconnect.
    - **Transcript View:** Auto-scrolling chat history.

## 8. Technology Stack
**Backend:**
- Python 3.11+
- FastAPI (REST API routing)
- LiveKit Server & Python SDK (WebRTC, VoicePipelineAgent)
- Pydantic AI (Structured LLM reasoning, Agent state)
- OpenAI API (or equivalent for LLM/TTS/STT via LiveKit plugins)

**Frontend:**
- React (Vite)
- Tailwind CSS
- Shadcn UI (Component library)
- `@agents-ui` (LiveKit Voice AI UI components)
- `@livekit/components-react` (WebRTC React hooks)

## 9. Security & Configuration
- **Authentication:** For MVP, simple unique session IDs. Production will require JWT-based user auth.
- **Configuration:** `.env` files for `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `OPENAI_API_KEY`.
- **Security Scope:** 
    - ✅ Secure generation of LiveKit WebRTC tokens in the backend.
    - ❌ Persistent data encryption (since MVP data is transient).

## 10. API Specification
- `POST /upload`: 
    - Request: `multipart/form-data` (file). 
    - Response: `{ "session_id": "uuid", "plan_summary": "..." }`
- `GET /token?session_id={id}`:
    - Response: `{ "token": "ey..." }`
- `GET /report?session_id={id}`:
    - Response: `{ "grades": {...}, "summary": "...", "recommendation": "..." }`

## 11. Success Criteria
- ✅ User can upload a resume and connect to a voice session seamlessly.
- ✅ The AI responds to voice inputs with latency < 800ms.
- ✅ The AI asks at least one context-aware follow-up question based on the user's answer.
- ✅ A valid JSON report is generated upon session completion.
- ✅ UI accurately reflects the connection state and active speaker.

## 12. Implementation Phases
**Phase 1: Foundation (Backend & Parsing)**
- Goal: Setup FastAPI and Pydantic AI resume parsing.
- Deliverables: ✅ `/upload` endpoint, ✅ `ResumeParserAgent` functional.
- Validation: Uploading a PDF returns a structured interview plan in the terminal.

**Phase 2: Real-time Voice (LiveKit Worker)**
- Goal: Establish the low-latency voice pipeline.
- Deliverables: ✅ LiveKit Worker script, ✅ `/token` endpoint, ✅ Basic echo/chat functionality.
- Validation: Connecting a basic client allows voice chat with the LLM.

**Phase 3: Hybrid Reasoning Integration**
- Goal: Connect Pydantic AI background tasks to the live interview.
- Deliverables: ✅ `evaluate_last_answer` tool, ✅ `ReportGeneratorAgent`, ✅ Phase transitions.
- Validation: AI dynamically shifts topics and generates a final report.

**Phase 4: Frontend Implementation**
- Goal: Build the React (Vite) and Shadcn interface.
- Deliverables: ✅ Visualizer, ✅ Control Bar, ✅ Transcript, ✅ Upload UI.
- Validation: Complete end-to-end user flow in the browser.

## 13. Future Considerations
- Video analysis (facial expression, eye contact).
- Integration with ATS (Applicant Tracking Systems) like Greenhouse or Lever.
- Multi-agent architecture (e.g., a "Technical Evaluator" agent passing off to a "Culture Fit" agent).

## 14. Risks & Mitigations
- **Risk:** High latency degrading the voice experience.
  - **Mitigation:** Use LiveKit's native `VoicePipelineAgent` with ultra-fast LLMs (e.g., GPT-4o-mini) and isolate deep reasoning to asynchronous background tasks.
- **Risk:** Agent interrupting the candidate prematurely.
  - **Mitigation:** Tune LiveKit VAD (Voice Activity Detection) settings for longer silence thresholds and handle interruptions gracefully in the state machine.
- **Risk:** Hallucinations in the final report.
  - **Mitigation:** Strictly enforce schema validation with Pydantic AI and provide the raw transcript as context to the reporting agent.