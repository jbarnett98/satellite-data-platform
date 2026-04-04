from fetch_satellite_data import fetch_satellite_data
from parse_tle_data import parse_tle_data
from enrich_satellite_data import enrich_satellite_data
from logger import setup_logger

import logging
import time

def run_pipeline():

    logger = setup_logger()

    start_time = time.time()

    logger.info("Starting satellite pipeline")

    try:

        logger.info("Step 1: Fetch satellite data")
        fetch_satellite_data()

        logger.info("Step 2: Parse TLE data")
        parse_tle_data()

        logger.info("Step 3: Enrich satellite data")
        enrich_satellite_data()

        logger.info("Pipeline completed successfully")


    except Exception as e:
        logger.error("Pipeline failed")
        logger.error(str(e))
    
    finally:

        end_time = time.time()
        runtime = round(end_time - start_time, 2)

        logger.info(f"Pipeline runtime: {runtime} seconds")

if __name__ == "__main__":
    run_pipeline()