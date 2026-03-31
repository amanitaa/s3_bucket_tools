import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import magic
import requests
from botocore.exceptions import ClientError

from s3_tool.logger import get_logger

logger = get_logger(__name__)

ALLOWED_MIME_TYPES = {
    "image/bmp",
    "image/jpeg",
    "image/png",
    "image/webp",
    "video/mp4",
}

ALLOWED_EXTENSIONS = {".bmp", ".jpg", ".jpeg", ".png", ".webp", ".mp4"}


def _detect_mime_type(file_path: str) -> str:
    mime = magic.Magic(mime=True)
    detected = mime.from_file(file_path)
    logger.debug("Detected MIME type for '%s': %s", file_path, detected)
    return detected


def _validate_file(file_path: str) -> None:
    mime_type = _detect_mime_type(file_path)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unsupported file type '{mime_type}'. "
            f"Allowed types: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )


def _guess_extension_from_mime(mime_type: str) -> str:
    mapping = {
        "image/bmp": ".bmp",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
    }
    return mapping.get(mime_type, "")


def download_file_and_upload_to_s3(
    s3_client,
    bucket_name: str,
    url: str,
    s3_key: str = None,
) -> str:
    logger.info("Downloading file from URL: %s", url)

    parsed = urlparse(url)
    original_filename = Path(parsed.path).name or "downloaded_file"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = os.path.join(tmp_dir, original_filename)

        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error("Failed to download file from '%s': %s", url, e)
            raise

        with open(tmp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info("File downloaded to temporary path: %s", tmp_path)

        _validate_file(tmp_path)

        mime_type = _detect_mime_type(tmp_path)
        ext = _guess_extension_from_mime(mime_type)

        if s3_key is None:
            stem = Path(original_filename).stem
            s3_key = f"{stem}{ext}"

        try:
            s3_client.upload_file(
                tmp_path,
                bucket_name,
                s3_key,
                ExtraArgs={"ContentType": mime_type},
            )
            logger.info(
                "Uploaded '%s' to s3://%s/%s", original_filename, bucket_name, s3_key
            )
        except ClientError as e:
            logger.error("Failed to upload file to S3: %s", e)
            raise

    return s3_key