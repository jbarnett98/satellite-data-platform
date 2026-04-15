import logging

from pipeline.scripts.fetch_satellite_data import fetch_satellite_data
from pipeline.scripts.fetch_satellite_metadata import fetch_satellite_metadata
from pipeline.scripts.process_satellite_data import process_satellite_data
from pipeline.scripts.store_in_sql import store_to_sql
from pipeline.scripts.store_metadata_in_sql import store_metadata_to_sql
from pipeline.scripts.generate_orbit_paths import generate_orbit_paths
from pipeline.scripts.generate_trajectory_samples import generate_trajectory_samples

logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    logger.info("Starting full satellite pipeline")

    fetch_result = fetch_satellite_data()
    if fetch_result == "not_updated":
        logger.info("No new upstream TLE data available")
    elif fetch_result is False:
        raise RuntimeError("TLE fetch step failed")

    metadata_result = fetch_satellite_metadata()
    if metadata_result is False:
        raise RuntimeError("Metadata fetch step failed")
    elif metadata_result == "not_updated":
        logger.info("Metadata file is still fresh; skipping metadata download")

    logger.info("Starting TLE processing step")
    process_satellite_data()

    logger.info("Loading TLE/orbital data to database")
    store_to_sql()

    logger.info("Loading metadata to database")
    store_metadata_to_sql()

    logger.info("Generating trajectory samples from satellites_latest")
    generate_trajectory_samples()

    logger.info("Generating orbit paths from satellites_latest")
    generate_orbit_paths()

    logger.info("Pipeline finished successfully")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_pipeline()