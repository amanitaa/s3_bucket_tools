import os
import math
from pathlib import Path

import magic
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

from s3_tool.logger import get_logger

logger = get_logger(__name__)

ALLOWED_MIME_TYPES = {
    "image/bmp",
    "image/jpeg",
    "image/png",
    "image/webp",
    "video/mp4",
    "text/csv",
    "application/pdf",
    "application/json",
    "text/plain",
}

MULTIPART_THRESHOLD_MB = 8
MULTIPART_CHUNKSIZE_MB = 8


def _detect_mime_type(file_path: str) -> str:
    mime = magic.Magic(mime=True)
    detected = mime.from_file(file_path)
    logger.debug("Detected MIME type for '%s': %s", file_path, detected)
    return detected


def _validate_mime(file_path: str) -> str:
    mime_type = _detect_mime_type(file_path)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unsupported file type '{mime_type}'.\n"
            f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )
    return mime_type


def upload_small_file(
    s3_client,
    bucket_name: str,
    local_path: str,
    s3_key: str = None,
    validate_mime: bool = False,
) -> str:
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"File not found: {local_path}")

    size_mb = os.path.getsize(local_path) / (1024 * 1024)
    logger.debug("File size: %.2f MB", size_mb)

    if validate_mime:
        mime_type = _validate_mime(local_path)
    else:
        mime_type = _detect_mime_type(local_path)

    if s3_key is None:
        s3_key = Path(local_path).name

    try:
        s3_client.upload_file(
            local_path,
            bucket_name,
            s3_key,
            ExtraArgs={"ContentType": mime_type},
        )
        logger.info("Uploaded (standard) '%s' -> s3://%s/%s", local_path, bucket_name, s3_key)
    except ClientError as e:
        logger.error("Upload failed: %s", e)
        raise

    return s3_key


def upload_large_file(
    s3_client,
    bucket_name: str,
    local_path: str,
    s3_key: str = None,
    validate_mime: bool = False,
    chunk_size_mb: int = MULTIPART_CHUNKSIZE_MB,
) -> str:
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"File not found: {local_path}")

    size_bytes = os.path.getsize(local_path)
    size_mb = size_bytes / (1024 * 1024)
    logger.info("Starting multipart upload for %.2f MB file.", size_mb)

    if validate_mime:
        mime_type = _validate_mime(local_path)
    else:
        mime_type = _detect_mime_type(local_path)

    if s3_key is None:
        s3_key = Path(local_path).name

    chunk_bytes = chunk_size_mb * 1024 * 1024
    total_parts = math.ceil(size_bytes / chunk_bytes)
    logger.info("Uploading in %d part(s) of %d MB each.", total_parts, chunk_size_mb)

    config = TransferConfig(
        multipart_threshold=MULTIPART_THRESHOLD_MB * 1024 * 1024,
        multipart_chunksize=chunk_bytes,
        use_threads=True,
    )

    uploaded_parts = {"count": 0}

    def progress_callback(bytes_transferred):
        uploaded_parts["count"] += bytes_transferred
        done = uploaded_parts["count"] / size_bytes * 100
        logger.debug("Progress: %.1f%%", done)

    try:
        s3_client.upload_file(
            local_path,
            bucket_name,
            s3_key,
            ExtraArgs={"ContentType": mime_type},
            Config=config,
            Callback=progress_callback,
        )
        logger.info("Multipart upload complete: s3://%s/%s", bucket_name, s3_key)
    except ClientError as e:
        logger.error("Multipart upload failed: %s", e)
        raise

    return s3_key


def set_lifecycle_policy(s3_client, bucket_name: str, days: int = 120, prefix: str = "") -> None:
    rule = {
        "ID": f"auto-delete-after-{days}-days",
        "Status": "Enabled",
        "Filter": {"Prefix": prefix},
        "Expiration": {"Days": days},
    }

    lifecycle_config = {"Rules": [rule]}

    try:
        s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration=lifecycle_config,
        )
        logger.info(
            "Lifecycle policy set on '%s': delete objects%s after %d days.",
            bucket_name,
            f" with prefix '{prefix}'" if prefix else "",
            days,
        )
    except ClientError as e:
        logger.error("Failed to set lifecycle policy: %s", e)
        raise


def get_lifecycle_policy(s3_client, bucket_name: str) -> list | None:
    try:
        response = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
        return response.get("Rules", [])
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchLifecycleConfiguration":
            return None
        raise