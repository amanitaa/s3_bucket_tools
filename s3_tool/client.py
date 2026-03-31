import os
import boto3
from dotenv import load_dotenv
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from s3_tool.logger import get_logger

load_dotenv()

logger = get_logger(__name__)


def init_client():
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_session_token = os.getenv("AWS_SESSION_TOKEN")
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    if not aws_access_key_id or not aws_secret_access_key:
        logger.error("AWS credentials not found. Check your .env file.")
        raise EnvironmentError("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set in .env")

    try:
        client = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region,
            aws_session_token=aws_session_token,
        )
        logger.info("S3 client initialized successfully (region: %s)", region)
        return client
    except (NoCredentialsError, PartialCredentialsError) as e:
        logger.error("Failed to initialize S3 client: %s", e)
        raise