import logging
import time

import requests

from pipeline.scripts.config import RAW_DATA_PATH, CELESTRAK_URL
from pipeline.scripts.s3_utils import upload_latest_tle, upload_archived_tle, download_latest_tle

logger = logging.getLogger(__name__)

MIN_RAW_BYTES = 10_000
MIN_RAW_LINES = 1_000


def _write_raw_file(content: bytes) -> None:
    RAW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = RAW_DATA_PATH.with_suffix(".tmp")

    with open(tmp_path, "wb") as f:
        f.write(content)

    tmp_path.replace(RAW_DATA_PATH)


def _validate_raw_content(full_content: bytes) -> str | None:
    decoded_preview = full_content[:2048].decode("utf-8", errors="ignore")

    if "GP data has not updated" in decoded_preview:
        return "not_updated"

    line_count = full_content.count(b"\n")
    byte_count = len(full_content)

    if byte_count < MIN_RAW_BYTES:
        raise ValueError(
            f"Downloaded file too small ({byte_count} bytes), refusing to overwrite raw data"
        )

    if line_count < MIN_RAW_LINES:
        raise ValueError(
            f"Downloaded file has too few lines ({line_count}), refusing to overwrite raw data"
        )

    logger.info("Validated downloaded data: %d bytes across %d lines", byte_count, line_count)
    return None


def _use_s3_fallback(reason: str, return_status: str) -> str | bool:
    logger.warning("%s Attempting to use latest raw TLE snapshot from S3.", reason)

    fallback_content = download_latest_tle()
    if fallback_content:
        _write_raw_file(fallback_content)
        logger.warning("Using fallback TLE data from S3")
        return return_status

    logger.error("No fallback TLE data available in S3")
    return False


def fetch_satellite_data(retries=3, delay=5):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SatelliteDataPipeline/1.0)"
    }

    for attempt in range(1, retries + 1):
        try:
            logger.info("Fetching satellite data (attempt %d)", attempt)

            response = requests.get(
                CELESTRAK_URL,
                timeout=30,
                headers=headers,
                stream=True,
            )

            if response.status_code != 200:
                preview = response.text[:500] if response.text else ""

                if "GP data has not updated" in preview:
                    logger.info("No new satellite data available from CelesTrak")
                    return _use_s3_fallback(
                        reason="CelesTrak reported no update.",
                        return_status="not_updated",
                    )

                logger.warning(
                    "Fetch attempt %d returned status %d. Response preview: %r",
                    attempt,
                    response.status_code,
                    preview,
                )
                response.raise_for_status()

            content_chunks = []
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content_chunks.append(chunk)

            if not content_chunks:
                raise ValueError("Downloaded response was empty")

            full_content = b"".join(content_chunks)

            validation_result = _validate_raw_content(full_content)
            if validation_result == "not_updated":
                logger.info("No new satellite data available from downloaded content")
                return _use_s3_fallback(
                    reason="Downloaded content indicates no update.",
                    return_status="not_updated",
                )

            upload_latest_tle(full_content)
            upload_archived_tle(full_content)
            _write_raw_file(full_content)

            logger.info("Satellite data downloaded to %s", RAW_DATA_PATH)
            return True

        except requests.exceptions.RequestException as e:
            logger.warning("Fetch attempt %d failed with request error: %s", attempt, e)
            if attempt < retries:
                logger.info("Retrying in %d seconds...", delay)
                time.sleep(delay)
            else:
                logger.error("All fetch attempts failed with request errors")
                break

        except Exception as e:
            logger.warning("Fetch attempt %d failed validation or S3 upload: %s", attempt, e)
            if attempt < retries:
                logger.info("Retrying in %d seconds...", delay)
                time.sleep(delay)
            else:
                logger.error("All fetch attempts failed validation")
                break

    return _use_s3_fallback(
        reason="All upstream fetch attempts failed.",
        return_status="fallback_used",
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetch_satellite_data()