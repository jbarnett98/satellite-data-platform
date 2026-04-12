import requests
from pathlib import Path
import logging
import time
from pipeline.scripts.config import RAW_DATA_PATH, CELESTRAK_URL

logger = logging.getLogger(__name__)

def fetch_satellite_data(retries=3, delay=5):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SatelliteDataPipeline/1.0)"
    }

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Fetching satellite data (attempt {attempt})")

            response = requests.get(
                CELESTRAK_URL,
                timeout=10,
                headers=headers,
                stream=True 
            )

            response.raise_for_status()

            # Check first chunk for "not updated"
            first_chunk = next(response.iter_content(chunk_size=1024)).decode("utf-8", errors="ignore")
            if "GP data has not updated" in first_chunk:
                logger.info("No new satellite data available — skipping update")
                return "not_updated"

            RAW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = RAW_DATA_PATH.with_suffix(".tmp")

            with open(tmp_path, "wb") as f:
                f.write(first_chunk.encode())  # write first chunk

               
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            tmp_path.replace(RAW_DATA_PATH)

            logger.info(f"Satellite data downloaded to {RAW_DATA_PATH}")
            return True

        except requests.exceptions.RequestException as e:
            logger.warning(f"Fetch attempt {attempt} failed: {e}")
            if attempt < retries:
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error("All fetch attempts failed")
                return False