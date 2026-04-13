import logging
import time

import requests

from pipeline.scripts.config import RAW_DATA_PATH, CELESTRAK_URL

logger = logging.getLogger(__name__)

MIN_RAW_BYTES = 10_000
MIN_RAW_LINES = 1_000


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
                logger.warning(
                    "Fetch attempt %d returned status %d. Response preview: %r",
                    attempt,
                    response.status_code,
                    preview,
                )
                response.raise_for_status()

            RAW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = RAW_DATA_PATH.with_suffix(".tmp")

            content_chunks = []
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content_chunks.append(chunk)

            if not content_chunks:
                raise ValueError("Downloaded response was empty")

            full_content = b"".join(content_chunks)
            decoded_preview = full_content[:2048].decode("utf-8", errors="ignore")

            if "GP data has not updated" in decoded_preview:
                logger.info("No new satellite data available — skipping update")
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

            with open(tmp_path, "wb") as f:
                f.write(full_content)

            tmp_path.replace(RAW_DATA_PATH)

            logger.info("Satellite data downloaded to %s", RAW_DATA_PATH)
            logger.info("Downloaded %d bytes across %d lines", byte_count, line_count)
            return True

        except requests.exceptions.RequestException as e:
            logger.warning("Fetch attempt %d failed with request error: %s", attempt, e)
            if attempt < retries:
                logger.info("Retrying in %d seconds...", delay)
                time.sleep(delay)
            else:
                logger.error("All fetch attempts failed")
                return False

        except Exception as e:
            logger.warning("Fetch attempt %d failed validation: %s", attempt, e)
            if attempt < retries:
                logger.info("Retrying in %d seconds...", delay)
                time.sleep(delay)
            else:
                logger.error("All fetch attempts failed validation")
                return False