import pytest
import json
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from api.main import app
from models.schemas import FinalReport, SectionGrade, InterviewPlan
from db.database import async_session
from db.crud import create_session, update_session_report


def _sample_report() -> FinalReport:
    return FinalReport(
        candidate_name="Jane Smith",
        overall_score=80,
        section_grades=[SectionGrade(section_name="Technical", score=8, comments="Good")],
        strengths=["Python"],
        weaknesses=["CSS"],
        recommendation="Hire",
        summary="Good candidate.",
    )


def _sample_plan() -> InterviewPlan:
    return InterviewPlan(
        candidate_name="Jane Smith",
        extracted_skills=["Python"],
        question_bank=["Q1"],
    )


async def _create_test_session(candidate_name="Jane Smith"):
    plan = InterviewPlan(
        candidate_name=candidate_name,
        extracted_skills=["Python"],
        question_bank=["Q1"],
    )
    async with async_session() as db:
        session = await create_session(
            db,
            user_id="test-user-id",
            candidate_name=candidate_name,
            plan_json=plan.model_dump_json(),
        )
        return session.id


async def _create_test_session_with_report(candidate_name="Jane Smith"):
    plan = _sample_plan()
    report = _sample_report()
    async with async_session() as db:
        session = await create_session(
            db,
            user_id="test-user-id",
            candidate_name=candidate_name,
            plan_json=plan.model_dump_json(),
        )
        await update_session_report(db, session.id, report.model_dump_json())
        return session.id


@pytest.mark.asyncio
async def test_save_transcript_returns_200():
    session_id = await _create_test_session()
    payload = {"candidate_name": "Jane Smith", "entries": [{"speaker": "Interviewer", "text": "Hello", "timestamp_s": 0.0}]}
    with patch("api.main.archive_transcript"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(f"/transcript/{session_id}", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "success"}


@pytest.mark.asyncio
async def test_download_transcript_returns_file():
    session_id = await _create_test_session_with_report()
    transcript_data = json.dumps([{"speaker": "Candidate", "text": "Hi", "timestamp_s": 1.5}]).encode()

    with patch("api.main.get_artifact", return_value=transcript_data):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/download/{session_id}/transcript")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert "attachment" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_download_pdf_returns_file():
    session_id = await _create_test_session_with_report()

    with patch("api.main.get_artifact", return_value=b"%PDF-fake"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/download/{session_id}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"


@pytest.mark.asyncio
async def test_download_invalid_file_type_returns_400():
    session_id = await _create_test_session_with_report()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/download/{session_id}/invalid")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_download_missing_session_returns_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/download/nonexistent/transcript")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_missing_artifact_returns_404():
    session_id = await _create_test_session_with_report()

    with patch("api.main.get_artifact", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/download/{session_id}/transcript")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_transcript_falls_back_to_database():
    session_id = await _create_test_session_with_report()
    payload = {"candidate_name": "Jane Smith", "entries": [{"speaker": "Candidate", "text": "Stored", "timestamp_s": 2.0}]}
    with patch("api.main.archive_transcript"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post(f"/transcript/{session_id}", json=payload)
    with patch("api.main.get_artifact", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/download/{session_id}/transcript")
    assert response.status_code == 200
    assert json.loads(response.content)[0]["text"] == "Stored"


@pytest.mark.asyncio
async def test_download_pdf_falls_back_to_database_report():
    session_id = await _create_test_session_with_report()
    with patch("api.main.get_artifact", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/download/{session_id}/pdf")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


@patch("utils.storage.Minio")
def test_archive_transcript_calls_put_object(mock_minio_cls):
    mock_client = MagicMock()
    mock_minio_cls.return_value = mock_client
    mock_client.bucket_exists.return_value = True

    from utils.storage import archive_transcript
    archive_transcript("sess-t2", "Jane Smith", b'[{"speaker":"Candidate","text":"Hi","timestamp_s":1.5}]')

    assert mock_client.put_object.call_count == 1
    call_args = mock_client.put_object.call_args[0]
    assert call_args[1] == "jane-smith_sess-t2/transcript.json"


@patch("utils.storage.Minio")
def test_get_artifact_returns_data(mock_minio_cls):
    mock_client = MagicMock()
    mock_minio_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.read.return_value = b"file-content"
    mock_client.get_object.return_value = mock_response

    from utils.storage import get_artifact
    result = get_artifact("sess-t3", "Jane Smith", "transcript.json")

    assert result == b"file-content"
    mock_client.get_object.assert_called_once_with("reports", "jane-smith_sess-t3/transcript.json")


@patch("utils.storage.Minio")
def test_get_artifact_returns_none_on_error(mock_minio_cls):
    mock_client = MagicMock()
    mock_minio_cls.return_value = mock_client
    mock_client.get_object.side_effect = Exception("not found")

    from utils.storage import get_artifact
    result = get_artifact("sess-t4", "Jane Smith", "transcript.json")

    assert result is None
