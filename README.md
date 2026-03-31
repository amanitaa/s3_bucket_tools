# S3 Tool

A comfortable CLI tool for managing AWS S3 buckets — covering tasks 4–8 from the lecture series.

## Stack

| Library | Purpose |
|---|---|
| **Poetry** | Dependency & virtual env management |
| **Click** | CLI argument parsing |
| **boto3** | AWS SDK |
| **python-dotenv** | Load credentials from `.env` |
| **python-magic** | MIME type detection (not just extension) |
| **logging** | Console + file logging (`s3_tool.log`) |

---

## Setup

```bash
# 1. Install dependencies
poetry install

# 2. Create your .env from the example
cp .env.example .env
# Then fill in your AWS credentials
```

**.env**
```
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1
```

```bash
# 3. Activate shell
poetry shell

# OR prefix every command with:
poetry run s3-tool <command>
```

---

## All Commands

### Bucket Management

```bash
s3-tool list-buckets
s3-tool create-bucket my-bucket --region eu-west-1
s3-tool delete-bucket my-bucket --force
s3-tool bucket-exists my-bucket
```

### Policy & ACL

```bash
s3-tool create-policy my-bucket                          # public read for /dev and /test
s3-tool create-policy my-bucket --prefix staging --prefix prod
s3-tool read-policy my-bucket
s3-tool set-acl my-bucket images/photo.jpg --acl public-read
```

---

### Upload Files + Lifecycle

```bash
# Small file upload (standard)
s3-tool upload my-bucket photo.jpg

# Large file upload (multipart)
s3-tool upload my-bucket big-video.mp4 --large

# Large file with custom chunk size and custom S3 key
s3-tool upload my-bucket big-video.mp4 --large --chunk-mb 16 --key videos/big-video.mp4

# With MIME type validation (rejects unsupported formats)
s3-tool upload my-bucket photo.jpg --validate-mime

# Set lifecycle policy: auto-delete after 120 days
s3-tool set-lifecycle my-bucket

# Custom: delete after 30 days, only objects under 'tmp/' prefix
s3-tool set-lifecycle my-bucket --days 30 --prefix tmp/

# View current lifecycle rules
s3-tool get-lifecycle my-bucket
```

**Supported MIME types when --validate-mime is used:**
`image/bmp`, `image/jpeg`, `image/png`, `image/webp`, `video/mp4`,
`text/csv`, `application/pdf`, `application/json`, `text/plain`

---

### Delete a Specific Object

```bash
# The -del flag is required as explicit confirmation
s3-tool delete-object my-bucket images/photo.jpg -del
```

---

### Versioning

```bash
# Check versioning status
s3-tool versioning-status my-bucket

# Check and enable in one command
s3-tool versioning-status my-bucket --enable

# List all versions of a file (newest first)
s3-tool list-versions my-bucket images/photo.jpg

# Output example:
#   Versions of s3://my-bucket/images/photo.jpg  (3 total)
#   #    Version ID                             Created                Size  Note
#   1    abc123...                              2024-01-15 10:00:00    50120  <-- latest
#   2    def456...                              2024-01-14 09:00:00    49800
#   3    ghi789...                              2024-01-13 08:00:00    49500

# Restore previous version as new latest
s3-tool restore-version my-bucket images/photo.jpg
```

---

### Organize by Extension

```bash
# Preview without making changes
s3-tool organize my-bucket --dry-run

# Actually reorganize
s3-tool organize my-bucket
```

**Example:**

Before:
```
image.jpg
demo.csv
users.csv
report.pdf
```

After:
```
jpg/image.jpg
csv/demo.csv
csv/users.csv
pdf/report.pdf
```