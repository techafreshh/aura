import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from api.main import app
from models.schemas import FinalReport, SectionGrade
from utils.pdf_report import generate_report_pdf


def _sample_report() -> FinalReport:
    return FinalReport(
        candidate_name="Test User",
        overall_score=85,
        section_grades=[SectionGrade(section_name="Technical", score=9, comments="Strong")],
        strengths=["Python", "System Design"],
        weaknesses=["CSS"],
        recommendation="Hire",
        summary="Excellent candidate.",
    )


def test_generate_report_pdf_valid():
    pdf = generate_report_pdf(_sample_report())
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 100


@patch("utils.storage.Minio")
def test_archive_report_calls_put_object(mock_minio_cls):
    mock_client = MagicMock()
    mock_minio_cls.return_value = mock_client
    mock_client.bucket_exists.return_value = True

    from utils.storage import archive_report

    archive_report("sess-1", {"key": "val", "candidate_name": "John Doe"}, b"fake-pdf")

    assert mock_client.put_object.call_count == 2
    calls = mock_client.put_object.call_args_list
    assert calls[0][0][1] == "john-doe_sess-1/report.json"
    assert calls[1][0][1] == "john-doe_sess-1/report.pdf"


@patch("utils.storage.Minio")
def test_archive_report_creates_bucket_if_missing(mock_minio_cls):
    mock_client = MagicMock()
    mock_minio_cls.return_value = mock_client
    mock_client.bucket_exists.return_value = False

    from utils.storage import archive_report

    archive_report("sess-2", {}, b"pdf")

    mock_client.make_bucket.assert_called_once()


@patch("utils.storage.Minio")
def test_archive_report_does_not_raise_on_error(mock_minio_cls):
    mock_minio_cls.side_effect = Exception("connection refused")

    from utils.storage import archive_report

    # Should not raise
    archive_report("sess-3", {}, b"pdf")


@pytest.mark.asyncio
async def test_save_report_returns_200():
    report_data = _sample_report().model_dump()
    with patch("api.main.archive_report"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/report/test-session", json=report_data)
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
