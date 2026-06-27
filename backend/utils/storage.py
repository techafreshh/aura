import os
import io
import json
import logging
import re
from minio import Minio

logger = logging.getLogger("storage")


def _get_client() -> Minio:
    return Minio(
        os.environ.get("MINIO_ENDPOINT", "minio:9000"),
        access_key=os.environ.get("MINIO_ACCESS_KEY", ""),
        secret_key=os.environ.get("MINIO_SECRET_KEY", ""),
        secure=False,
    )


def _ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def archive_report(session_id: str, report_dict: dict, pdf_bytes: bytes) -> None:
    """Upload report JSON and PDF to MinIO. Logs errors, never raises."""
    try:
        client = _get_client()
        bucket = os.environ.get("MINIO_BUCKET", "reports")
        _ensure_bucket(client, bucket)

        json_data = json.dumps(report_dict).encode()
        name_slug = re.sub(r"[^a-z0-9]+", "-", report_dict.get("candidate_name", "unknown").lower()).strip("-")
        folder = f"{name_slug}_{session_id}"
        client.put_object(bucket, f"{folder}/report.json", io.BytesIO(json_data), len(json_data))
        client.put_object(bucket, f"{folder}/report.pdf", io.BytesIO(pdf_bytes), len(pdf_bytes))

        logger.info("Archived report %s to MinIO", session_id)
    except Exception as e:
        logger.error("Failed to archive report %s: %s", session_id, e)


def archive_pdf(session_id: str, candidate_name: str, pdf_bytes: bytes) -> None:
    """Upload a styled PDF to MinIO for the given session. Logs errors, never raises."""
    try:
        client = _get_client()
        bucket = os.environ.get("MINIO_BUCKET", "reports")
        _ensure_bucket(client, bucket)
        name_slug = re.sub(r"[^a-z0-9]+", "-", candidate_name.lower()).strip("-")
        folder = f"{name_slug}_{session_id}"
        client.put_object(bucket, f"{folder}/report.pdf", io.BytesIO(pdf_bytes), len(pdf_bytes))
        logger.info("Archived PDF %s to MinIO", session_id)
    except Exception as e:
        logger.error("Failed to archive PDF %s: %s", session_id, e)


def archive_transcript(session_id: str, candidate_name: str, transcript_data: bytes) -> None:
    """Upload transcript JSON to MinIO. Logs errors, never raises."""
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


def get_artifact(session_id: str, candidate_name: str, filename: str) -> bytes | None:
    """Download an artifact from MinIO. Returns None on failure."""
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
    except Exception as e:
        logger.warning("Failed to get artifact %s/%s: %s", session_id, filename, e)
        return None