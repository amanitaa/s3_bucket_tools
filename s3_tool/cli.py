import json
import sys
from email import policy

import click
from botocore.exceptions import ClientError

from requests.exceptions import HTTPError

from s3_tool.client import init_client
from s3_tool.bucket_ops import list_buckets, create_bucket, delete_bucket, bucket_exists
from s3_tool.object_ops import download_file_and_upload_to_s3
from s3_tool.policy_ops import (
    generate_public_read_policy,
    create_bucket_policy,
    read_bucket_policy,
    set_object_access_policy,
)
from s3_tool.upload_ops import (
    upload_small_file,
    upload_large_file,
    set_lifecycle_policy,
    get_lifecycle_policy,
)
from s3_tool.advanced_ops import (
    delete_object,
    get_versioning_status,
    enable_versioning,
    list_object_versions,
    restore_previous_version,
    organize_by_extension,
)


@click.group()
@click.pass_context
def cli(ctx):
    """S3 Tool — a comfortable CLI for AWS S3 bucket management."""
    ctx.ensure_object(dict)
    ctx.obj["client"] = init_client()



@cli.command("list-buckets")
@click.pass_context
def cmd_list_buckets(ctx):
    """List all S3 buckets."""
    buckets = list_buckets(ctx.obj["client"])
    if not buckets:
        click.echo("No buckets found.")
        return
    click.echo(f"\n{'Name':<45} {'Created'}")
    click.echo("-" * 70)
    for b in buckets:
        click.echo(f"{b['Name']:<45} {b['CreationDate'].strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"\nTotal: {len(buckets)} bucket(s)")


@cli.command("create-bucket")
@click.argument("bucket_name")
@click.option("--region", default=None, help="AWS region (default from .env)")
@click.pass_context
def cmd_create_bucket(ctx, bucket_name, region):
    """Create a bucket."""
    try:
        created = create_bucket(ctx.obj["client"], bucket_name, region)

        if created:
            click.echo(f"Bucket '{bucket_name}' created successfully.")
        else:
            click.echo(f"Bucket '{bucket_name}' already exists in your account.")

    except PermissionError as e:
        click.echo(f"{str(e)}", err=True)

    except RuntimeError as e:
        click.echo(f"{str(e)}", err=True)

    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}", err=True)
        raise click.ClickException(str(e)) from None


@cli.command("delete-bucket")
@click.argument("bucket_name")
@click.option("--force", is_flag=True, help="Empty bucket before deleting.")
@click.pass_context
def cmd_delete_bucket(ctx, bucket_name, force):
    """Delete a bucket (use --force to empty it first)."""
    deleted = delete_bucket(ctx.obj["client"], bucket_name, force)
    if deleted:
        click.echo(f"Bucket '{bucket_name}' deleted.")
    else:
        click.echo(f"Bucket '{bucket_name}' does not exist.")


@cli.command("bucket-exists")
@click.argument("bucket_name")
@click.pass_context
def cmd_bucket_exists(ctx, bucket_name):
    """Check whether a bucket exists."""
    exists = bucket_exists(ctx.obj["client"], bucket_name)
    if exists:
        click.echo(f"Bucket '{bucket_name}' exists.")
    else:
        click.echo(f"Bucket '{bucket_name}' does not exist.")


@cli.command("upload-from-url")
@click.argument("bucket_name")
@click.argument("url")
@click.option("--key", default=None, help="S3 object key (auto-detected if omitted)")
@click.pass_context
def cmd_upload_from_url(ctx, bucket_name, url, key):
    """Download a file from a URL and upload it to S3 with MIME validation."""
    try:
        s3_key = download_file_and_upload_to_s3(ctx.obj["client"], bucket_name, url, key)
        click.echo(f"Uploaded to s3://{bucket_name}/{s3_key}")
    except ValueError as e:
        click.echo(f"Validation error: {e}", err=True)
        sys.exit(1)
    except HTTPError as e:
        click.echo(f"HTTPError: {e}", err=True)
        sys.exit(1)
    except ClientError as e:
        click.echo(f"ClientError: {e}", err=True)


@cli.command("set-acl")
@click.argument("bucket_name")
@click.argument("object_key")
@click.option(
    "--acl",
    default="public-read",
    show_default=True,
    type=click.Choice([
        "private", "public-read", "public-read-write",
        "authenticated-read", "bucket-owner-read", "bucket-owner-full-control",
    ]),
)
@click.pass_context
def cmd_set_acl(ctx, bucket_name, object_key, acl):
    """Set ACL on an S3 object."""
    try:
        set_object_access_policy(ctx.obj["client"], bucket_name, object_key, acl)
        click.echo(f"ACL '{acl}' applied to s3://{bucket_name}/{object_key}")
    except ClientError as e:
        click.echo(f"Failed to set ACL on object {object_key} in bucket {bucket_name}: {e}", err=True)


@cli.command("create-policy")
@click.argument("bucket_name")
@click.option("--prefix", multiple=True, default=("dev", "test"), show_default=True)
@click.pass_context
def cmd_create_policy(ctx, bucket_name, prefix):
    """Create a public-read bucket policy for the given prefixes."""
    client = ctx.obj["client"]
    try:
        existing = read_bucket_policy(client, bucket_name)
        if existing:
            click.echo(f"Bucket '{bucket_name}' already has a policy:")
            click.echo(json.dumps(existing, indent=2))
            return
    except ClientError as e:
        click.echo(f"Failed to read policy for bucket: {bucket_name} : {e}", err=True)

    try:
        public_policy = generate_public_read_policy(bucket_name, list(prefix))
        create_bucket_policy(client, bucket_name, public_policy)
        click.echo(f"Policy applied for prefixes: {', '.join(prefix)}")
        click.echo(json.dumps(public_policy, indent=2))
    except ClientError as e:
        click.echo(f"Failed to create policy for bucket: {bucket_name} : {e}", err=True)


@cli.command("read-policy")
@click.argument("bucket_name")
@click.pass_context
def cmd_read_policy(ctx, bucket_name):
    """Print the current bucket policy."""
    try:
        if existing := read_bucket_policy(ctx.obj["client"], bucket_name):
            click.echo(json.dumps(existing, indent=2))
        else:
            click.echo(f"Bucket '{bucket_name}' has no policy.")
    except ClientError as e:
        click.echo(f"Failed to read policy for bucket: {bucket_name} : {e}", err=True)


@cli.command("upload")
@click.argument("bucket_name")
@click.argument("file_path")
@click.option("--key", default=None, help="S3 key (defaults to filename)")
@click.option("--large", is_flag=True, help="Force multipart upload for large files.")
@click.option("--validate-mime", is_flag=True, help="Reject unsupported MIME types.")
@click.option("--chunk-mb", default=8, show_default=True, help="Chunk size in MB (multipart only).")
@click.pass_context
def cmd_upload(ctx, bucket_name, file_path, key, large, validate_mime, chunk_mb):
    """Upload a local file to S3.

    \b
    Small file:  s3-tool upload my-bucket photo.jpg
    Large file:  s3-tool upload my-bucket video.mp4 --large
    With MIME:   s3-tool upload my-bucket photo.jpg --validate-mime
    """
    try:
        if large:
            s3_key = upload_large_file(
                ctx.obj["client"], bucket_name, file_path, key,
                validate_mime=validate_mime, chunk_size_mb=chunk_mb,
            )
            click.echo(f"Multipart upload complete: s3://{bucket_name}/{s3_key}")
        else:
            s3_key = upload_small_file(
                ctx.obj["client"], bucket_name, file_path, key,
                validate_mime=validate_mime,
            )
            click.echo(f"Upload complete: s3://{bucket_name}/{s3_key}")
    except (ValueError, FileNotFoundError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("set-lifecycle")
@click.argument("bucket_name")
@click.option("--days", default=120, show_default=True, help="Delete objects after N days.")
@click.option("--prefix", default="", show_default=True, help="Apply only to objects with this prefix.")
@click.pass_context
def cmd_set_lifecycle(ctx, bucket_name, days, prefix):
    """Set a lifecycle policy that auto-deletes objects after N days."""
    set_lifecycle_policy(ctx.obj["client"], bucket_name, days, prefix)
    msg = f"Lifecycle policy set: objects"
    if prefix:
        msg += f" under '{prefix}'"
    msg += f" will be deleted after {days} day(s)."
    click.echo(msg)


@cli.command("get-lifecycle")
@click.argument("bucket_name")
@click.pass_context
def cmd_get_lifecycle(ctx, bucket_name):
    """Show the lifecycle policy of a bucket."""
    rules = get_lifecycle_policy(ctx.obj["client"], bucket_name)
    if rules is None:
        click.echo(f"Bucket '{bucket_name}' has no lifecycle policy.")
    else:
        click.echo(json.dumps(rules, indent=2, default=str))


@cli.command("delete-object")
@click.argument("bucket_name")
@click.argument("key")
@click.option("-del", "--confirm-delete", is_flag=True, required=True,
              help="Required confirmation flag to delete the object.")
@click.pass_context
def cmd_delete_object(ctx, bucket_name, key, confirm_delete):
    """Delete a specific object from a bucket.

    \b
    Requires the -del flag as explicit confirmation.
    Example:
        s3-tool delete-object my-bucket images/photo.jpg -del
    """
    delete_object(ctx.obj["client"], bucket_name, key)
    click.echo(f"Deleted s3://{bucket_name}/{key}")


@cli.command("versioning-status")
@click.argument("bucket_name")
@click.option("--enable", is_flag=True, help="Enable versioning if currently off.")
@click.pass_context
def cmd_versioning_status(ctx, bucket_name, enable):
    """Check (and optionally enable) versioning on a bucket."""
    client = ctx.obj["client"]
    status = get_versioning_status(client, bucket_name)

    if status == "Enabled":
        click.echo(f"Versioning is ENABLED on '{bucket_name}'.")
    else:
        click.echo(f"Versioning is {status or 'DISABLED'} on '{bucket_name}'.")
        if enable:
            enable_versioning(client, bucket_name)
            click.echo(f"Versioning has been enabled on '{bucket_name}'.")


@cli.command("list-versions")
@click.argument("bucket_name")
@click.argument("key")
@click.pass_context
def cmd_list_versions(ctx, bucket_name, key):
    """List all versions of an object (newest first)."""
    versions = list_object_versions(ctx.obj["client"], bucket_name, key)
    if not versions:
        click.echo(f"No versions found for '{key}'.")
        return

    click.echo(f"\nVersions of s3://{bucket_name}/{key}  ({len(versions)} total)\n")
    click.echo(f"  {'#':<4} {'Version ID':<36} {'Created':<22} {'Size':>10}  Note")
    click.echo("  " + "-" * 84)
    for i, v in enumerate(versions):
        note = "<-- latest" if i == 0 else ""
        size = v.get("Size", 0)
        click.echo(
            f"  {i+1:<4} {v['VersionId']:<36} "
            f"{v['LastModified'].strftime('%Y-%m-%d %H:%M:%S'):<22} "
            f"{size:>10}  {note}"
        )


@cli.command("restore-version")
@click.argument("bucket_name")
@click.argument("key")
@click.pass_context
def cmd_restore_version(ctx, bucket_name, key):
    """Restore the previous version of an object as the new latest version."""
    restored = restore_previous_version(ctx.obj["client"], bucket_name, key)
    if restored:
        click.echo(f"Restored version '{restored}' as new latest for '{key}'.")
    else:
        click.echo(f"No previous version available for '{key}'. Nothing to restore.")


@cli.command("organize")
@click.argument("bucket_name")
@click.option("--dry-run", is_flag=True, help="Preview moves without modifying anything.")
@click.pass_context
def cmd_organize(ctx, bucket_name, dry_run):
    """Organize bucket objects into sub-folders by file extension.

    \b
    Before:  image.jpg  demo.csv  users.csv
    After:   jpg/image.jpg  csv/demo.csv  csv/users.csv

    Prints a summary:
        csv - 2
        jpg - 1
    """
    if dry_run:
        click.echo(f"[DRY RUN] Previewing reorganization of '{bucket_name}'...\n")
    else:
        click.echo(f"Organizing '{bucket_name}' by file extension...\n")

    counts = organize_by_extension(ctx.obj["client"], bucket_name, dry_run=dry_run)

    if not counts:
        click.echo("Nothing to move — bucket is empty or already organized.")
        return

    click.echo("\n-- Summary " + ("(dry run) " if dry_run else "") + "-----------------")
    for ext, count in sorted(counts.items()):
        click.echo(f"  {ext} - {count}")
    click.echo(f"\n  Total files moved: {sum(counts.values())}")


if __name__ == "__main__":
    cli()
