# s3-tool

A developer-friendly CLI for managing AWS S3 buckets. Covers bucket operations, file uploads (standard & multipart), lifecycle policies, versioning, and object organization — all from the terminal.

## Tech Stack

| Library | Purpose |
|---|---|
| [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) | AWS SDK for Python |
| [Click](https://click.palletsprojects.com/) | CLI framework |
| [python-magic](https://github.com/ahupp/python-magic) | MIME type detection (content-based, not extension-based) |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | Load AWS credentials from `.env` |
| [Poetry](https://python-poetry.org/) | Dependency & virtualenv management |

---

## Requirements

- Python 3.10+
- Poetry
- AWS account with S3 access

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/amanitaa/s3-tool.git
cd s3-tool

# 2. Install dependencies
poetry install

# 3. Set up credentials
cp .env.example .env
```

Edit `.env` with your AWS credentials:

```env
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1
```

```bash
# 4. Activate the virtualenv
poetry shell

# Or prefix every command with:
poetry run s3-tool <command>
```

---

## Project Structure

```
s3_tool/
├── cli.py          # CLI entry point — all Click commands
├── client.py       # boto3 client initialization
├── bucket_ops.py   # Bucket CRUD
├── object_ops.py   # Upload from URL
├── upload_ops.py   # File upload (standard + multipart) & lifecycle
├── policy_ops.py   # Bucket policies & ACLs
├── advanced_ops.py # Versioning, object deletion, organize by extension
└── logger.py       # Logging setup (console + s3_tool.log)
```

---

## Commands

### Bucket Management

```bash
s3-tool list-buckets
s3-tool create-bucket my-bucket
s3-tool create-bucket my-bucket --region eu-west-1
s3-tool delete-bucket my-bucket
s3-tool delete-bucket my-bucket --force   # empty bucket first, then delete
s3-tool bucket-exists my-bucket
```

---

### Upload Files

```bash
# Standard upload
s3-tool upload my-bucket photo.jpg

# Multipart upload (recommended for large files)
s3-tool upload my-bucket big-video.mp4 --large

# Custom S3 key and chunk size
s3-tool upload my-bucket big-video.mp4 --large --key videos/big-video.mp4 --chunk-mb 16

# Reject unsupported MIME types before uploading
s3-tool upload my-bucket photo.jpg --validate-mime
```

**Allowed MIME types** (when `--validate-mime` is used):
`image/bmp`, `image/jpeg`, `image/png`, `image/webp`, `video/mp4`, `text/csv`, `application/pdf`, `application/json`, `text/plain`

---

### Upload from URL

```bash
# Download a file from a URL and upload it directly to S3
s3-tool upload-from-url my-bucket https://example.com/photo.jpg

# Specify a custom S3 key
s3-tool upload-from-url my-bucket https://example.com/photo.jpg --key images/photo.jpg
```

---

### Lifecycle Policies

Automatically expire (delete) objects after a set number of days.

```bash
# Default: delete all objects after 120 days
s3-tool set-lifecycle my-bucket

# Delete objects under 'tmp/' after 30 days
s3-tool set-lifecycle my-bucket --days 30 --prefix tmp/

# View current lifecycle rules
s3-tool get-lifecycle my-bucket
```

---

### Bucket Policy & ACL

```bash
# Create a public-read policy for /dev and /test prefixes (default)
s3-tool create-policy my-bucket

# Custom prefixes
s3-tool create-policy my-bucket --prefix staging --prefix prod

# Read the current policy
s3-tool read-policy my-bucket

# Set ACL on a specific object
s3-tool set-acl my-bucket images/photo.jpg --acl public-read
```

Available ACL values: `private`, `public-read`, `public-read-write`, `authenticated-read`, `bucket-owner-read`, `bucket-owner-full-control`

---

### Delete an Object

```bash
# The -del flag is required as explicit confirmation
s3-tool delete-object my-bucket images/photo.jpg -del
```

---

### Versioning

```bash
# Check versioning status
s3-tool versioning-status my-bucket

# Check status and enable versioning in one step
s3-tool versioning-status my-bucket --enable

# List all versions of an object (newest first)
s3-tool list-versions my-bucket images/photo.jpg
```

Example output of `list-versions`:

```
Versions of s3://my-bucket/images/photo.jpg  (3 total)

  #    Version ID                             Created                      Size  Note
  ---------------------------------------------------------------------------------
  1    abc123...                              2024-01-15 10:00:00         50120  <-- latest
  2    def456...                              2024-01-14 09:00:00         49800
  3    ghi789...                              2024-01-13 08:00:00         49500
```

```bash
# Restore the previous version as the new latest
s3-tool restore-version my-bucket images/photo.jpg
```

---

### Organize by Extension

Moves objects into sub-folders named after their file extension.

```bash
# Preview without making any changes
s3-tool organize my-bucket --dry-run

# Apply reorganization
s3-tool organize my-bucket
```

**Before:**
```
image.jpg
demo.csv
users.csv
report.pdf
```

**After:**
```
jpg/image.jpg
csv/demo.csv
csv/users.csv
pdf/report.pdf
```

---

## Logging

All operations are logged to both the console and `s3_tool.log` in the project root. Use this file to audit or debug any S3 interactions.

---