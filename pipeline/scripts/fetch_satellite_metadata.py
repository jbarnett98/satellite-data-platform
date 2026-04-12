import logging
import time
from pathlib import Path

import requests

from pipeline.scripts.config import METADATA_DATA_PATH, CELESTRAK_SATCAT_URL

logger = logging.getLogger(__name__)


def fetch_satellite_metadata(retries: int = 3, delay: int = 5):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SatelliteDataPipeline/1.0)"
    }

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