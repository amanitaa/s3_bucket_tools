import json
from botocore.exceptions import ClientError
from s3_tool.logger import get_logger

logger = get_logger(__name__)


def _disable_block_public_access(s3_client, bucket_name: str) -> None:
    s3_client.delete_public_access_block(Bucket=bucket_name)
    logger.info("Public access block removed for bucket '%s'.", bucket_name)


def generate_public_read_policy(bucket_name: str, prefixes: list[str] = None) -> dict:
    if prefixes is None:
        prefixes = ["dev", "test"]

    statements = []
    for prefix in prefixes:
        statements.append(
            {
                "Sid": f"PublicRead_{prefix.replace('/', '_')}",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket_name}/{prefix.strip('/')}/*",
            }
        )

    policy = {
        "Version": "2012-10-17",
        "Statement": statements,
    }

    logger.debug("Generated policy for bucket '%s': %s", bucket_name, json.dumps(policy))
    return policy


def create_bucket_policy(s3_client, bucket_name: str, policy: dict) -> None:
    try:
        _disable_block_public_access(s3_client, bucket_name)
        s3_client.put_bucket_policy(
            Bucket=bucket_name,
            Policy=json.dumps(policy),
        )
        logger.info("Policy applied to bucket '%s'.", bucket_name)
    except ClientError as e:
        logger.error("Failed to set policy on bucket '%s': %s", bucket_name, e)
        raise


def read_bucket_policy(s3_client, bucket_name: str) -> dict | None:
    try:
        response = s3_client.get_bucket_policy(Bucket=bucket_name)
        policy = json.loads(response["Policy"])
        logger.info("Retrieved policy for bucket '%s'.", bucket_name)
        return policy
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
            logger.info("Bucket '%s' has no policy.", bucket_name)
            return None
        logger.error("Failed to read policy for bucket '%s': %s", bucket_name, e)
        raise


def set_object_access_policy(s3_client, bucket_name: str, object_key: str, acl: str = "public-read") -> None:
    valid_acls = {
        "private",
        "public-read",
        "public-read-write",
        "authenticated-read",
        "aws-exec-read",
        "bucket-owner-read",
        "bucket-owner-full-control",
    }

    if acl not in valid_acls:
        raise ValueError(f"Invalid ACL '{acl}'. Valid options: {', '.join(sorted(valid_acls))}")

    try:
        _disable_block_public_access(s3_client, bucket_name)
        s3_client.put_object_acl(
            Bucket=bucket_name,
            Key=object_key,
            ACL=acl,
        )
        logger.info("ACL '%s' set on s3://%s/%s", acl, bucket_name, object_key)
    except ClientError as e:
        logger.error(
            "Failed to set ACL on object '%s' in bucket '%s': %s",
            object_key,
            bucket_name,
            e,
        )
        raise