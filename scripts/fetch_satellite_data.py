import requests
from pathlib import Path
import logging
from config import RAW_DATA_PATH, CELESTRAK_URL

logger = logging.getLogger(__name__)

def fetch_satellite_data():

    logger.info("Attempting URL")

    response = requests.get(CELESTRAK_URL)

    text = response.text

    if "GP data has not updated" in text:
        logger.warning("No new satellite data available — keeping existing file")
        return

    RAW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(RAW_DATA_PATH, "w") as f:
        f.write(text)

    logger.info(f"Satellite data downloaded to {RAW_DATA_PATH}")

if __name__ == "__main__":
    fetch_satellite_data()

    