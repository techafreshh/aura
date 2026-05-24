# Plan: Interview Timestamped Transcript

## Summary

Capture a timestamped transcript in the worker process, upload it to MinIO in the same folder as the existing report, and add a download proxy endpoint + frontend "Download" dropdown to access all artifacts (PDF + transcript).

## User Story

As an interviewer/admin
I want each interview to produce a timestamped transcript
So that I can review the exact conversation later

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | worker, backend API, storage, frontend |
| Jira Issue | N/A |

---

## Patterns to Follow

### Storage Upload
```python
# SOURCE: backend/utils/storage.py:24-37
def archive_report(session_id: str, report_dict: dict, pdf_bytes: bytes) -> None:
    try:
        client = _get_client()
        bucket = os.environ.get("MINIO_BUCKET", "reports")
        _ensure_bucket(client, bucket)
        json_data = json.dumps(report_dict).encode()
        name_slug = re.sub(r"[^a-z0-9]+", "-", report_dict.get("candidate_name", "unknown").lower()).strip("-")
        folder = f"{name_slug}_{session_id}"
        client.put_object(bucket, f"{folder}/report.json", io.BytesIO(json_data), len(json_data))
        client.put_object(bucket, f"{folder}/report.pdf", io.BytesIO(pdf_bytes), len(pdf_bytes))
    except Exception as e:
        logger.error("Failed to archive report %s: %s", session_id, e)
```

### Worker Event Handlers
```python
# SOURCE: backend/agent/worker.py:131-145
@session.on("user_input_transcribed")
def on_user_input(ev):
    if ev.is_final:
        workflow.context.transcript_lines.append(f"Candidate: {ev.transcript}")

@ctx.room.on("participant_disconnected")
def on_participant_left(participant):
    nonlocal report_task
    report_task = asyncio.ensure_future(generate_and_save_report(workflow.context, session_id))
```

### Worker Report POST
```python
# SOURCE: backend/agent/worker.py:56-67
backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
async with httpx.AsyncClient() as client:
    response = await client.post(
        f"{backend_url}/report/{session_id}",
        json=report.model_dump()
    )
```

### API Test Pattern
```python
# SOURCE: backend/tests/test_storage.py:27-36
@patch("utils.storage.Minio")
def test_archive_report_calls_put_object(mock_minio_cls):
    mock_client = MagicMock()
    mock_minio_cls.return_value = mock_client
    mock_client.bucket_exists.return_value = True
    from utils.storage import archive_report
    archive_report("sess-1", {"key": "val", "candidate_name": "John Doe"}, b"fake-pdf")
    assert mock_client.put_object.call_count == 2
```

### Frontend API Client
```typescript
// SOURCE: frontend/src/api/client.ts:49-52
export const getReport = async (sessionId: string): Promise<FinalReport> => {
  const response = await api.get<FinalReport>(`/report/${sessionId}`);
  return response.data;
};
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/agent/worker.py` | UPDATE | Timestamped transcript capture + POST to backend |
| `backend/utils/storage.py` | UPDATE | Add `archive_transcript` and `get_artifact` functions |
| `backend/api/main.py` | UPDATE | Add `POST /transcript/{session_id}` + `GET /download/{session_id}/{file_type}` |
| `frontend/src/api/client.ts` | UPDATE | Add `getDownloadUrl` helper |
| `frontend/src/components/interview/ReportView.tsx` | UPDATE | Replace "Export PDF" with "Download" dropdown |
| `frontend/src/pages/InterviewFlow.tsx` | UPDATE | Pass `sessionId` to ReportView |

---

## Tasks

### Task 1: Add timestamped transcript to InterviewContext

- **File**: `backend/agent/worker.py`
- **Action**: UPDATE
- **Implement**:
  - Import `time` at top
  - Add `start_time: float = 0.0` field to `InterviewContext` dataclass
  - Change `transcript_lines: list` to `transcript: list = field(default_factory=list)` (list of dicts)
  - In `entrypoint`, set `workflow.context.start_time = time.time()` after session creation
  - Update `on_user_input` handler: append `{"speaker": "Candidate", "text": ev.transcript, "timestamp_s": round(time.time() - workflow.context.start_time, 2)}`
  - Update `on_conversation_item` handler: same dict format with `"speaker": "Interviewer"`
  - Update `generate_and_save_report`: build `transcript_text` from `"\n".join(f"{e['speaker']}: {e['text']}" for e in context.transcript)`
  - After report POST succeeds, POST transcript to backend:
    ```python
    await client.post(
        f"{backend_url}/transcript/{session_id}",
        json={"candidate_name": context.plan.candidate_name, "entries": context.transcript},
    )
    ```
- **Mirror**: `backend/agent/worker.py:131-145`
- **Validate**: `cd backend && uv run python -c "from agent.worker import InterviewContext"`

### Task 2: Add storage functions for transcript

- **File**: `backend/utils/storage.py`
- **Action**: UPDATE
- **Implement**:
  - Add `archive_transcript(session_id: str, candidate_name: str, transcript_data: bytes) -> None`:
    ```python
    def archive_transcript(session_id: str, candidate_name: str, transcript_data: bytes) -> None:
        try:
            client = _get_client()
            bucket = os.environ.get("MINIO_BUCKET", "reports")
            _ensure_bucket(client, bucket)
            name_slug = re.sub(r"[^a-z0-9]+", "-", candidate_name.lower()).strip("-")
            folder = f"{name_slug}_{session_id}"
            client.put_object(bucket, f"{folder}/transcript.json", io.BytesIO(transcript_data), len(transcript_data))
            logger.info("Archived transcript %s to MinIO", session_id)
        except Exception as e:
            logger.error("Failed to archive transcript %s: %s", session_id, e)
    ```
  - Add `get_artifact(session_id: str, candidate_name: str, filename: str) -> bytes | None`:
    ```python
    def get_artifact(session_id: str, candidate_name: str, filename: str) -> bytes | None:
        try:
            client = _get_client()
            bucket = os.environ.get("MINIO_BUCKET", "reports")
            name_slug = re.sub(r"[^a-z0-9]+", "-", candidate_name.lower()).strip("-")
            folder = f"{name_slug}_{session_id}"
            response = client.get_object(bucket, f"{folder}/{filename}")
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except Exception:
            return None
    ```
- **Mirror**: `backend/utils/storage.py:24-37`
- **Validate**: `cd backend && uv run pytest tests/test_storage.py`

### Task 3: Add transcript and download endpoints

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**:
  - Import `from fastapi.responses import Response` and `from utils.storage import archive_transcript, get_artifact`
  - Add `POST /transcript/{session_id}`:
    ```python
    @app.post("/transcript/{session_id}")
    async def save_transcript(session_id: str, payload: dict, background_tasks: BackgroundTasks):
        def _archive():
            archive_transcript(session_id, payload.get("candidate_name", "unknown"), json.dumps(payload.get("entries", [])).encode())
        background_tasks.add_task(_archive)
        return {"status": "success"}
    ```
  - Add `GET /download/{session_id}/{file_type}`:
    ```python
    @app.get("/download/{session_id}/{file_type}")
    async def download_artifact(session_id: str, file_type: str):
        report = reports.get(session_id)
        if not report:
            raise HTTPException(404, "Session not found")
        file_map = {"transcript": ("transcript.json", "application/json"), "pdf": ("report.pdf", "application/pdf")}
        entry = file_map.get(file_type)
        if not entry:
            raise HTTPException(400, "Invalid file type. Use: transcript, pdf")
        filename, content_type = entry
        data = get_artifact(session_id, report.candidate_name, filename)
        if not data:
            raise HTTPException(404, "File not found")
        return Response(content=data, media_type=content_type, headers={"Content-Disposition": f"attachment; filename={filename}"})
    ```
  - Add `import json` if not already imported
- **Mirror**: `backend/api/main.py:82-90`
- **Validate**: `cd backend && uv run pytest tests/test_api.py`

### Task 4: Update frontend API client

- **File**: `frontend/src/api/client.ts`
- **Action**: UPDATE
- **Implement**:
  - Add:
    ```typescript
    export const getDownloadUrl = (sessionId: string, fileType: 'pdf' | 'transcript'): string => {
      return `${BASE_URL}/download/${sessionId}/${fileType}`;
    };
    ```
- **Mirror**: `frontend/src/api/client.ts:49-52`
- **Validate**: `cd frontend && npm run build`

### Task 5: Replace "Export PDF" with "Download" dropdown

- **File**: `frontend/src/components/interview/ReportView.tsx`
- **Action**: UPDATE
- **Implement**:
  - Add `sessionId: string` to `ReportViewProps`
  - Add state: `const [dropdownOpen, setDropdownOpen] = useState(false)`
  - Import `getDownloadUrl` from `@/api/client`
  - Replace the "Export PDF" buttons (nav icon button, page-head button, action-bar button) with a dropdown:
    - Primary button: "Download" with chevron
    - On click: toggle `dropdownOpen`
    - Dropdown menu (absolutely positioned):
      - "PDF Report" → calls existing `handleExportPDF()`
      - "Transcript (.json)" → `window.open(getDownloadUrl(sessionId, 'transcript'), '_blank')`
    - Close dropdown on outside click or after selection
  - Keep existing `handleExportPDF` logic unchanged
- **Mirror**: Existing `.btn` / `.btn-primary` styling in ReportView
- **Validate**: `cd frontend && npm run build`

### Task 6: Pass sessionId to ReportView

- **File**: `frontend/src/pages/InterviewFlow.tsx`
- **Action**: UPDATE
- **Implement**:
  - Change `<ReportView report={report} onDone={reset} />` to `<ReportView report={report} sessionId={sessionId!} onDone={reset} />`
- **Mirror**: `frontend/src/pages/InterviewFlow.tsx:52`
- **Validate**: `cd frontend && npm run build`

---

## Validation

```bash
# Backend
cd backend
uv run pytest

# Frontend
cd frontend
npm run build
```

---

## Acceptance Criteria

- [ ] Timestamped transcript captured with speaker + elapsed seconds for each utterance
- [ ] Transcript uploaded to MinIO as `transcript.json` in the same folder as the report
- [ ] `GET /download/{session_id}/transcript` returns the transcript JSON
- [ ] `GET /download/{session_id}/pdf` returns the report PDF
- [ ] Frontend "Download" dropdown offers PDF and Transcript options
- [ ] Existing report generation still works unchanged
- [ ] All existing tests pass
- [ ] No new dependencies required
