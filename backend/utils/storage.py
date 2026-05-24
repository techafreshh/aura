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
