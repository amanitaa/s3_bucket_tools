import json
import sys
from pathlib import Path

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
    _detect_mime_type,
    _folder_from_mime,
)
from s3_tool.advanced_ops import (
    delete_object,
    get_versioning_status,
    enable_versioning,
    list_object_versions,
    restore_previous_version,
    rollback_to_first_version,
    delete_old_versions,
    organize_by_extension,
    host_static_website,
    set_website_hosting,
    get_website_hosting,
    delete_website_hosting,
)


@click.group()
@click.pass_context
def cli(ctx):
    """S3 Tool — a comfortable CLI for AWS S3 bucket management."""
    ctx.ensure_object(dict)
    ctx.obj["client"] = init_client()


@cli.command("host")
@click.argument("bucket_name")
@click.option(
    "--source", required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Local folder to upload as the website root.",
)
@click.option("--index", default="index.html", show_default=True, help="Index document filename.")
@click.option("--error", default="error.html", show_default=True, help="Error document filename.")
@click.pass_context
def cmd_host(ctx, bucket_name, source, index, error):
    """Deploy a local folder as a public S3 static website.

    \b
    1. Uploads every file preserving directory structure.
    2. Enables static website hosting.
    3. Applies a public-read bucket policy.
    4. Prints the website URL.

    \b
    Example:
      s3-tool host my-static-site --source ./html_demo_site
    """
    try:
        url = host_static_website(
            ctx.obj["client"], bucket_name, source,
            index_doc=index, error_doc=error,
        )
        click.echo(f"\nWebsite is live at:\n  {url}\n")
    except NotADirectoryError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except (PermissionError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ClientError as e:
        click.echo(f"AWS Error: {e}", err=True)
        sys.exit(1)


@cli.command("enable-website")
@click.argument("bucket_name")
@click.option("--index", default="index.html", show_default=True, help="Index document filename.")
@click.option("--error", default="error.html", show_default=True, help="Error document filename.")
@click.pass_context
def cmd_enable_website(ctx, bucket_name, index, error):
    """Enable static website hosting on a bucket."""
    try:
        set_website_hosting(ctx.obj["client"], bucket_name, index, error)
        region = ctx.obj["client"].meta.region_name
        click.echo(f"Static website hosting enabled on '{bucket_name}'.")
        click.echo(f"  Index document : {index}")
        click.echo(f"  Error document : {error}")
        click.echo(f"  Endpoint       : http://{bucket_name}.s3-website-{region}.amazonaws.com")
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)


@cli.command("get-website")
@click.argument("bucket_name")
@click.pass_context
def cmd_get_website(ctx, bucket_name):
    """Show the static website hosting configuration of a bucket."""
    try:
        config = get_website_hosting(ctx.obj["client"], bucket_name)
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)
        return

    if config is None:
        click.echo(f"Bucket '{bucket_name}' has no website hosting configuration.")
        return

    index = config.get("IndexDocument", {}).get("Suffix", "-")
    error = config.get("ErrorDocument", {}).get("Key", "-")
    region = ctx.obj["client"].meta.region_name
    click.echo(f"Website hosting on '{bucket_name}':")
    click.echo(f"  Index document : {index}")
    click.echo(f"  Error document : {error}")
    click.echo(f"  Endpoint       : http://{bucket_name}.s3-website-{region}.amazonaws.com")


@cli.command("disable-website")
@click.argument("bucket_name")
@click.pass_context
def cmd_disable_website(ctx, bucket_name):
    """Disable static website hosting on a bucket."""
    try:
        delete_website_hosting(ctx.obj["client"], bucket_name)
        click.echo(f"Static website hosting disabled on '{bucket_name}'.")
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)


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
@click.option("--key", default=None, help="S3 key (defaults to filename).")
@click.option("--large", is_flag=True, help="Force multipart upload for large files.")
@click.option("--validate-mime", is_flag=True, help="Reject unsupported MIME types.")
@click.option("--chunk-mb", default=8, show_default=True, help="Chunk size in MB (multipart only).")
@click.option(
    "--by-mime", is_flag=True,
    help=(
        "Auto-route the file into a sub-folder named after its detected extension "
        "(e.g. jpg/, mp4/, pdf/). python-magic inspects file content, not the extension."
    ),
)
@click.pass_context
def cmd_upload(ctx, bucket_name, file_path, key, large, validate_mime, chunk_mb, by_mime):
    """Upload a local file to S3.

    \b
    Small file:       s3-tool upload my-bucket photo.jpg
    Large file:       s3-tool upload my-bucket video.mp4 --large
    MIME validation:  s3-tool upload my-bucket photo.jpg --validate-mime
    Auto-folder:      s3-tool upload my-bucket data.csv --by-mime
                      -> s3://my-bucket/csv/data.csv
    """
    try:
        if by_mime:
            mime_type = _detect_mime_type(file_path)
            folder = _folder_from_mime(mime_type)
            filename = key if key else Path(file_path).name
            key = f"{folder}/{filename}"

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
    try:
        set_lifecycle_policy(ctx.obj["client"], bucket_name, days, prefix)
        msg = f"Lifecycle policy set: objects"
        if prefix:
            msg += f" under '{prefix}'"
        msg += f" will be deleted after {days} day(s)."
        click.echo(msg)
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)


@cli.command("get-lifecycle")
@click.argument("bucket_name")
@click.pass_context
def cmd_get_lifecycle(ctx, bucket_name):
    """Show the lifecycle policy of a bucket."""
    try:
        if (rules := get_lifecycle_policy(ctx.obj["client"], bucket_name)) is None:
            click.echo(f"Bucket '{bucket_name}' has no lifecycle policy.")
        else:
            click.echo(json.dumps(rules, indent=2, default=str))
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)


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
    try:
        delete_object(ctx.obj["client"], bucket_name, key)
        click.echo(f"Deleted s3://{bucket_name}/{key}")
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)


@cli.command("versioning")
@click.argument("bucket_name")
@click.option("--enable", is_flag=True, help="Enable versioning if currently off.")
@click.option("--list", "list_key", default=None, metavar="KEY", help="List all versions of an object.")
@click.option("--restore", "restore_key", default=None, metavar="KEY", help="Restore the previous version of an object.")
@click.option("--rollback", "rollback_key", default=None, metavar="KEY", help="Rollback an object to its first (oldest) version.")
@click.option("--purge", "purge_keys", multiple=True, metavar="KEY", help="Delete old versions of an object (repeatable).")
@click.option("--months", default=6, show_default=True, help="Used with --purge: delete versions older than N months.")
@click.option("--dry-run", is_flag=True, help="Used with --purge: preview deletions without removing anything.")
@click.option("--include-latest", is_flag=True, help="Used with --purge: also purge the latest version if old enough.")
@click.pass_context
def cmd_versioning(ctx, bucket_name, enable, list_key, restore_key, rollback_key,
                   purge_keys, months, dry_run, include_latest):
    """Manage object versioning on a bucket.

    \b
    Show status:    s3-tool versioning my-bucket
    Enable:         s3-tool versioning my-bucket --enable
    List versions:  s3-tool versioning my-bucket --list photo.jpg
    Restore prev:   s3-tool versioning my-bucket --restore photo.jpg
    Rollback first: s3-tool versioning my-bucket --rollback photo.jpg
    Purge old:      s3-tool versioning my-bucket --purge photo.jpg --purge video.mp4
                    s3-tool versioning my-bucket --purge photo.jpg --months 3 --dry-run
    """
    client = ctx.obj["client"]
    try:
        if list_key:
            versions = list_object_versions(client, bucket_name, list_key)
            if not versions:
                click.echo(f"No versions found for '{list_key}'.")
                return
            click.echo(f"\nVersions of s3://{bucket_name}/{list_key}  ({len(versions)} total)\n")
            click.echo(f"  {'#':<4} {'Version ID':<36} {'Created':<22} {'Size':>10}  Note")
            click.echo("  " + "-" * 84)
            for i, v in enumerate(versions):
                note = "<-- latest" if i == 0 else ""
                click.echo(
                    f"  {i+1:<4} {v['VersionId']:<36} "
                    f"{v['LastModified'].strftime('%Y-%m-%d %H:%M:%S'):<22} "
                    f"{v.get('Size', 0):>10}  {note}"
                )

        elif restore_key:
            restored = restore_previous_version(client, bucket_name, restore_key)
            if restored:
                click.echo(f"Restored version '{restored}' as new latest for '{restore_key}'.")
            else:
                click.echo(f"No previous version available for '{restore_key}'. Nothing to restore.")

        elif rollback_key:
            restored = rollback_to_first_version(client, bucket_name, rollback_key)
            if restored:
                click.echo(f"Rolled back '{rollback_key}' to first version '{restored}'.")
            else:
                click.echo(f"No older version available for '{rollback_key}'. Nothing to rollback.")

        elif purge_keys:
            total = 0
            errors = 0
            for key in purge_keys:
                try:
                    count = delete_old_versions(
                        client, bucket_name, key,
                        months=months, dry_run=dry_run, include_latest=include_latest,
                    )
                    action = "Would delete" if dry_run else "Deleted"
                    if count:
                        click.echo(f"{action} {count} old version(s) for '{key}'.")
                    else:
                        click.echo(f"No versions older than {months} month(s) found for '{key}'.")
                    total += count
                except ClientError as e:
                    click.echo(f"Error processing '{key}': {e}", err=True)
                    errors += 1
            if len(purge_keys) > 1:
                action = "Would delete" if dry_run else "Deleted"
                click.echo(f"\n{action} {total} version(s) across {len(purge_keys)} object(s).")
            if errors:
                sys.exit(1)

        else:
            status = get_versioning_status(client, bucket_name)
            if status == "Enabled":
                click.echo(f"Versioning is ENABLED on '{bucket_name}'.")
            else:
                click.echo(f"Versioning is {status or 'DISABLED'} on '{bucket_name}'.")
                if enable:
                    enable_versioning(client, bucket_name)
                    click.echo(f"Versioning has been enabled on '{bucket_name}'.")

    except ClientError as e:
        click.echo(f"Error: {e}", err=True)


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

    try:
        counts = organize_by_extension(ctx.obj["client"], bucket_name, dry_run=dry_run)
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)
        return

    if not counts:
        click.echo("Nothing to move — bucket is empty or already organized.")
        return

    click.echo("\n-- Summary " + ("(dry run) " if dry_run else "") + "-----------------")
    for ext, count in sorted(counts.items()):
        click.echo(f"  {ext} - {count}")
    click.echo(f"\n  Total files moved: {sum(counts.values())}")


if __name__ == "__main__":
    cli()
