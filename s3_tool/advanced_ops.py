from collections import defaultdict
from botocore.exceptions import ClientError
from s3_tool.logger import get_logger

logger = get_logger(__name__)


def delete_object(s3_client, bucket_name: str, key: str) -> None:
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=key)
        logger.info("Deleted object s3://%s/%s", bucket_name, key)
    except ClientError:
        raise


def get_versioning_status(s3_client, bucket_name: str) -> str:
    try:
        response = s3_client.get_bucket_versioning(Bucket=bucket_name)
        status = response.get("Status", "Disabled")
        logger.info("Versioning status for '%s': %s", bucket_name, status)
        return status
    except ClientError as e:
        logger.error("Failed to get versioning status: %s", e)
        raise


def enable_versioning(s3_client, bucket_name: str) -> None:
    try:
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={"Status": "Enabled"},
        )
        logger.info("Versioning enabled on '%s'.", bucket_name)
    except ClientError as e:
        logger.error("Failed to enable versioning: %s", e)
        raise


def list_object_versions(s3_client, bucket_name: str, key: str) -> list[dict]:
    try:
        response = s3_client.list_object_versions(Bucket=bucket_name, Prefix=key)
        versions = [
            v for v in response.get("Versions", [])
            if v["Key"] == key
        ]
        versions.sort(key=lambda v: v["LastModified"], reverse=True)
        logger.info("Found %d version(s) for '%s'.", len(versions), key)
        return versions
    except ClientError as e:
        logger.error("Failed to list versions for '%s': %s", key, e)
        raise


def restore_previous_version(s3_client, bucket_name: str, key: str) -> str | None:
    versions = list_object_versions(s3_client, bucket_name, key)

    if len(versions) < 2:
        logger.warning("No previous version available for '%s'.", key)
        return None

    previous = versions[1]
    version_id = previous["VersionId"]
    logger.info("Restoring version '%s' for key '%s'.", version_id, key)

    copy_source = {
        "Bucket": bucket_name,
        "Key": key,
        "VersionId": version_id,
    }

    try:
        s3_client.copy_object(
            CopySource=copy_source,
            Bucket=bucket_name,
            Key=key,
        )
        logger.info("Previous version restored as new version for '%s'.", key)
        return version_id
    except ClientError as e:
        logger.error("Failed to restore previous version: %s", e)
        raise


def _list_all_objects(s3_client, bucket_name: str) -> list[str]:
    keys = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket_name):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def organize_by_extension(s3_client, bucket_name: str, dry_run: bool = False) -> dict[str, int]:
    keys = _list_all_objects(s3_client, bucket_name)

    if not keys:
        logger.info("Bucket '%s' is empty.", bucket_name)
        return {}

    moves: list[tuple[str, str]] = []

    for key in keys:
        if "/" in key:
            parts = key.split("/")
            filename = parts[-1]
            existing_folder = parts[0]
        else:
            filename = key
            existing_folder = None

        if not filename:
            continue

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "no_extension"
        target_key = f"{ext}/{filename}"

        if key == target_key:
            logger.debug("'%s' already in correct folder, skipping.", key)
            continue

        moves.append((key, target_key))

    counts: dict[str, int] = defaultdict(int)

    for source_key, target_key in moves:
        ext_folder = target_key.split("/")[0]
        if dry_run:
            logger.info("[DRY RUN] Would move: '%s' -> '%s'", source_key, target_key)
        else:
            try:
                s3_client.copy_object(
                    Bucket=bucket_name,
                    CopySource={"Bucket": bucket_name, "Key": source_key},
                    Key=target_key,
                )
                s3_client.delete_object(Bucket=bucket_name, Key=source_key)
                logger.info("Moved: '%s' -> '%s'", source_key, target_key)
            except ClientError as e:
                logger.error("Failed to move '%s': %s", source_key, e)
                continue

        counts[ext_folder] += 1

    return dict(counts)