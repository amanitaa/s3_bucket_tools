import json
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from botocore.exceptions import ClientError
from s3_tool.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://api.quotable.kurokeita.dev/api/quotes/random"
_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/111.0.0.0 Safari/537.36"
    ),
}


def get_quote(author: Optional[str] = None) -> dict:
    """Fetch a random quote from the Quotable API.

    If *author* is given, filter results to that author's name.
    """
    url = f"{_BASE_URL}?{urlencode({'author': author})}" if author else _BASE_URL
    try:
        with urlopen(Request(url, headers=_HEADERS)) as response:
            data = json.loads(response.read().decode())
            logger.debug("Fetched quote (author=%s)", author or "random")
            return data
    except Exception as e:
        logger.error("Failed to fetch quote: %s", e)
        raise


def format_quote(data: dict) -> str:
    """Return a human-readable string from an API response dict."""
    q = data.get("quote", {})
    content = q.get("content", "")
    author = q.get("author", {}).get("name", "Unknown")
    return f'"{content}"\n--- {author}'


def save_quote_to_s3(s3_client, bucket_name: str, data: dict) -> str:
    """Upload *data* as a JSON object to *bucket_name*.

    Key format: quotes/<author_slug>_<UTC-timestamp>.json
    Returns the S3 key.
    """
    author_name = data.get("quote", {}).get("author", {}).get("name", "unknown")
    author_slug = author_name.lower().replace(" ", "_")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    s3_key = f"quotes/{author_slug}_{timestamp}.json"

    payload = json.dumps(data, ensure_ascii=False, indent=2).encode()
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=payload,
            ContentType="application/json",
        )
        logger.info("Quote saved to s3://%s/%s", bucket_name, s3_key)
    except ClientError as e:
        logger.error("Failed to save quote: %s", e)
        raise
    return s3_key
