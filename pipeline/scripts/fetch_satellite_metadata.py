import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from pipeline.scripts.config import METADATA_DATA_PATH, CELESTRAK_SATCAT_URL

logger = logging.getLogger(__name__)

METADATA_REFRESH_HOURS = 24


def metadata_file_is_fresh(refresh_hours: int = METADATA_REFRESH_HOURS) -> bool:
    if not METADATA_DATA_PATH.exists():
        return False

    modified_ts = METADATA_DATA_PATH.stat().st_mtime
    modified_at = datetime.fromtimestamp(modified_ts, tz=timezone.utc)
    now = datetime.now(timezone.utc)

    age = now - modified_at
    is_fresh = age < timedelta(hours=refresh_hours)

    logger.info(
        "Metadata file age: %.2f hours | fresh=%s",
        age.total_seconds() / 3600.0,
        is_fresh,
    )
    return is_fresh


def fetch_satellite_metadata(
    retries: int = 3,
    delay: int = 5,
    force: bool = False,
) -> str | bool:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SatelliteDataPipeline/1.0)"
    }

    if not force and metadata_file_is_fresh():
        logger.info("Skipping metadata download; local file is still fresh")
        return "not_updated"

    for attempt in range(1, retries + 1):
        try:
            logger.info("Fetching satellite metadata (attempt %d)", attempt)

            response = requests.get(
                CELESTRAK_SATCAT_URL,
                timeout=30,
                headers=headers,
            )
            response.raise_for_status()

            METADATA_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = METADATA_DATA_PATH.with_suffix(".tmp")

            with open(tmp_path, "wb") as f:
                f.write(response.content)

            tmp_path.replace(METADATA_DATA_PATH)

            logger.info("Satellite metadata downloaded to %s", METADATA_DATA_PATH)
            return True

        except requests.exceptions.RequestException as e:
            logger.warning("Metadata fetch attempt %d failed: %s", attempt, e)
            if attempt < retries:
                logger.info("Retrying in %d seconds...", delay)
                time.sleep(delay)
            else:
                logger.error("All metadata fetch attempts failed")
                return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetch_satellite_metadata()