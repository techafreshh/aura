# Plan: MinIO Report Archival

## Summary

After an interview report is saved to memory, fire a background task that archives the report as both JSON and a generated PDF to the existing MinIO instance. This is purely write-only archival — MinIO is never read from during normal app operation. The existing user flow is unchanged.

## User Story

As a system operator
I want interview reports archived to persistent storage
So that reports survive container restarts and are available for future reference

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | backend |
| Jira Issue | N/A |

---

## Patterns to Follow

### Utility Module Structure
```python
# SOURCE: backend/utils/pdf_parser.py:1-18
import io
from pypdf import PdfReader

async def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extracts text from a PDF file provided as bytes.
    Raises ValueError if no text could be extracted.
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        text = text.strip()
        if not text:
            raise ValueError("No text could be extracted from the PDF.")
        return text
    except Exception as e:
        if isinstance(e, ValueError):
            raise e
        raise ValueError(f"Failed to parse PDF: {str(e)}")
```

### Endpoint Pattern (POST with side effects)
```python
# SOURCE: backend/api/main.py:80-83
@app.post("/report/{session_id}")
async def save_report(session_id: str, report: FinalReport):
    reports[session_id] = report
    return {"status": "success"}
```

### Test Pattern (async API tests with httpx)
```python
# SOURCE: backend/tests/test_api.py:10-15
@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
```

### Test Pattern (unit tests with mocks)
```python
# SOURCE: backend/tests/test_agents.py:10-25
@pytest.mark.asyncio
async def test_evaluator_agent():
    test_model = TestModel(custom_output_args={...})
    with evaluator_agent.override(model=test_model):
        result = await evaluator_agent.run("Test prompt")
    assert isinstance(result.output, EvaluationResult)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/pyproject.toml` | UPDATE | Add `minio` and `reportlab` dependencies |
| `backend/utils/storage.py` | CREATE | MinIO upload utility functions |
| `backend/utils/pdf_report.py` | CREATE | Generate PDF from FinalReport |
| `backend/api/main.py` | UPDATE | Add background task to archive report after save |
| `backend/tests/test_storage.py` | CREATE | Test MinIO archival logic |
| `.env.example` | UPDATE | Add MinIO env vars |
| `backend/.env.example` | UPDATE | Add MinIO env vars |
| `DEPLOY.md` | UPDATE | Document MinIO requirement |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Add dependencies

- **File**: `backend/pyproject.toml`
- **Action**: UPDATE
- **Implement**: Add `"minio>=7.2.0"` and `"reportlab>=4.0"` to the `dependencies` list
- **Mirror**: `backend/pyproject.toml:8-20` - follow existing dependency format
- **Validate**: `cd backend && uv sync`

### Task 2: Create MinIO storage utility

- **File**: `backend/utils/storage.py`
- **Action**: CREATE
- **Implement**:
  - Import `os`, `io`, `json`, `logging` and `from minio import Minio`
  - Create module-level logger: `logger = logging.getLogger("storage")`
  - `_get_client() -> Minio` — reads `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` from env, returns `Minio(endpoint, access_key, secret_key, secure=False)`
  - `_ensure_bucket(client, bucket)` — calls `client.bucket_exists(bucket)`, creates if missing
  - `archive_report(session_id: str, report_dict: dict, pdf_bytes: bytes)` — gets client, ensures bucket from `MINIO_BUCKET` env (default `"reports"`), uploads `{session_id}.json` (JSON-serialized bytes) and `{session_id}.pdf` using `client.put_object`. Wrap in try/except, log errors, never raise.
- **Mirror**: `backend/utils/pdf_parser.py:1-18` - same module style (imports, docstrings, try/except)
- **Validate**: `cd backend && uv run python -c "from utils.storage import archive_report"`

### Task 3: Create PDF report generator

- **File**: `backend/utils/pdf_report.py`
- **Action**: CREATE
- **Implement**:
  - `generate_report_pdf(report: FinalReport) -> bytes`
  - Use `reportlab.lib.pagesizes.A4`, `reportlab.platypus.SimpleDocTemplate`, `Paragraph`, `Spacer`, `Table`
  - Build a clean PDF with: title (candidate name), overall score, recommendation, section grades table, strengths list, weaknesses list, summary paragraph
  - Return the PDF as bytes from a `BytesIO` buffer
- **Mirror**: `backend/utils/pdf_parser.py` - same style (io.BytesIO usage, function signature)
- **Validate**: `cd backend && uv run python -c "from utils.pdf_report import generate_report_pdf; from models.schemas import FinalReport, SectionGrade; r = FinalReport(candidate_name='Test', overall_score=80, section_grades=[SectionGrade(section_name='Tech', score=8, comments='Good')], strengths=['Python'], weaknesses=['CSS'], recommendation='Hire', summary='Good candidate'); pdf = generate_report_pdf(r); assert pdf[:4] == b'%%PDF'"`

### Task 4: Wire background archival into save_report endpoint

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**:
  - Add import: `from fastapi import BackgroundTasks` (add to existing import line)
  - Add import: `from utils.storage import archive_report`
  - Add import: `from utils.pdf_report import generate_report_pdf`
  - Modify `save_report` signature to accept `background_tasks: BackgroundTasks`
  - After `reports[session_id] = report`, add:
    ```python
    def _archive():
        pdf_bytes = generate_report_pdf(report)
        archive_report(session_id, report.model_dump(), pdf_bytes)
    background_tasks.add_task(_archive)
    ```
  - Return remains `{"status": "success"}`
- **Mirror**: `backend/api/main.py:80-83` - minimal modification to existing endpoint
- **Validate**: `cd backend && uv run python -c "from api.main import app"`

### Task 5: Add tests

- **File**: `backend/tests/test_storage.py`
- **Action**: CREATE
- **Implement**:
  - Test `generate_report_pdf` produces valid PDF bytes (starts with `%PDF`)
  - Test `archive_report` calls MinIO `put_object` twice (mock `minio.Minio`)
  - Test that `save_report` endpoint still returns 200 (existing test pattern)
- **Mirror**: `backend/tests/test_api.py:10-15` and `backend/tests/test_agents.py:10-25`
- **Validate**: `cd backend && $env:PYTHONPATH="." ; uv run pytest tests/test_storage.py -v`

### Task 6: Update environment configuration

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: Add MinIO section:
  ```
  # MinIO (report archival)
  MINIO_ENDPOINT=minio:9000
  MINIO_ACCESS_KEY=
  MINIO_SECRET_KEY=
  MINIO_BUCKET=reports
  ```
- **File**: `backend/.env.example`
- **Action**: UPDATE
- **Implement**: Add same MinIO vars
- **File**: `DEPLOY.md`
- **Action**: UPDATE
- **Implement**: Add a line under Prerequisites noting "MinIO instance (for report archival)" and list the env vars
- **Validate**: Visual inspection

---

## Validation

```bash
cd backend
$env:PYTHONPATH="."
uv sync
uv run pytest -v
```

---

## Acceptance Criteria

- [ ] All tasks completed
- [ ] `uv sync` installs without errors
- [ ] Tests pass
- [ ] POST /report/{session_id} still returns 200 immediately
- [ ] Background task uploads JSON + PDF to MinIO bucket
- [ ] Follows existing patterns (utility module style, test style, endpoint style)
