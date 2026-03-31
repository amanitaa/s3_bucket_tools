import os
from botocore.exceptions import ClientError
from s3_tool.logger import get_logger

logger = get_logger(__name__)


def bucket_exists(s3_client, bucket_name: str) -> bool:
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        logger.debug("Bucket '%s' exists and belongs to your account.", bucket_name)
        return True
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "404":
            logger.debug("Bucket '%s' does not exist.", bucket_name)
            return False
        if code == "403":
            raise PermissionError(
                f"Bucket name '{bucket_name}' is already taken by another AWS account. "
                "Please choose a different, more unique bucket name."
            )
        logger.error("Unexpected error checking bucket '%s': %s", bucket_name, e)
        raise


def list_buckets(s3_client) -> list[dict]:
    try:
        response = s3_client.list_buckets()
        buckets = response.get("Buckets", [])
        logger.info("Found %d bucket(s).", len(buckets))
        return buckets
    except ClientError as e:
        logger.error("Failed to list buckets: %s", e)
        raise


def create_bucket(s3_client, bucket_name: str, region: str = None) -> bool:
    region = region or os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    try:
        if bucket_exists(s3_client, bucket_name):
            logger.warning("Bucket '%s' already exists in your account.", bucket_name)
            return False
    except PermissionError as e:
        raise e

    try:
        if region == "us-east-1":
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        logger.info("Bucket '%s' created in region '%s'.", bucket_name, region)
        return True
    except ClientError as e:
        logger.error("Failed to create bucket '%s': %s", bucket_name, e)
        raise


def delete_bucket(s3_client, bucket_name: str, force: bool = False) -> bool:
    if not bucket_exists(s3_client, bucket_name):
        logger.warning("Bucket '%s' does not exist.", bucket_name)
        return False

    try:
        if force:
            logger.info("Force-deleting: emptying bucket '%s' first.", bucket_name)
            s3_resource = _get_resource_from_client(s3_client)
            bucket = s3_resource.Bucket(bucket_name)

            deleted_objects = 0
            for obj in bucket.objects.all():
                obj.delete()
                deleted_objects += 1

            deleted_versions = 0
            for version in bucket.object_versions.all():
                version.delete()
                deleted_versions += 1

            logger.info(
                "Removed %d object(s) and %d version(s) from '%s'.",
                deleted_objects,
                deleted_versions,
                bucket_name,
            )

        s3_client.delete_bucket(Bucket=bucket_name)
        logger.info("Bucket '%s' deleted successfully.", bucket_name)
        return True
    except ClientError as e:
        logger.error("Failed to delete bucket '%s': %s", bucket_name, e)
        raise


def _get_resource_from_client(s3_client):
    import boto3
    session = boto3.session.Session()
    credentials = s3_client._request_signer._credentials
    region = s3_client.meta.region_name
    return session.resource(
        "s3",
        aws_access_key_id=credentials.access_key,
        aws_secret_access_key=credentials.secret_key,
        aws_session_token=getattr(credentials, "token", None),
        region_name=region,
    )