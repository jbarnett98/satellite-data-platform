import json
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError

from pipeline.scripts.config import (
    AWS_REGION,
    S3_BUCKET,
    S3_LATEST_TLE_KEY,
    S3_ARCHIVE_PREFIX,
)

logger = logging.getLogger(__name__)

s3 = boto3.client("s3", region_name=AWS_REGION)


def upload_latest_tle(content: bytes) -> None:
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=S3_LATEST_TLE_KEY,
        Body=content,
        ContentType="text/plain",
    )
    logger.info("Uploaded latest TLE snapshot to s3://%s/%s", S3_BUCKET, S3_LATEST_TLE_KEY)


def upload_archived_tle(content: bytes) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    archive_key = f"{S3_ARCHIVE_PREFIX}{timestamp}.txt"

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=archive_key,
        Body=content,
        ContentType="text/plain",
    )
    logger.info("Uploaded archived TLE snapshot to s3://%s/%s", S3_BUCKET, archive_key)
    return archive_key


def download_latest_tle() -> bytes | None:
    try:
        response = s3.get_object(Bucket=S3_BUCKET, Key=S3_LATEST_TLE_KEY)
        content = response["Body"].read()
        logger.info("Downloaded fallback TLE snapshot from s3://%s/%s", S3_BUCKET, S3_LATEST_TLE_KEY)
        return content
    except (ClientError, NoCredentialsError, BotoCoreError) as e:
        logger.warning("Could not download fallback TLE snapshot from S3: %s", e)
        return None


def upload_json_object(key: str, payload: dict | list, log_upload: bool = False) -> None:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=body,
        ContentType="application/json",
        CacheControl="no-cache",
    )

    if log_upload:
        logger.info("Uploaded JSON artifact to s3://%s/%s", S3_BUCKET, key)