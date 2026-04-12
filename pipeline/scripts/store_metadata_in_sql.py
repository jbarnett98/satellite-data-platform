import logging
import pandas as pd
from sqlalchemy import create_engine

from pipeline.scripts.config import METADATA_DATA_PATH, SQLALCHEMY_DATABASE_URI

logger = logging.getLogger(__name__)

TABLE_NAME = "satellite_metadata"


def store_metadata_to_sql() -> None:
    logger.info("Loading satellite metadata from %s", METADATA_DATA_PATH)

    df = pd.read_csv(METADATA_DATA_PATH)

    if df.empty:
        raise ValueError("Metadata dataset is empty. Refusing to load empty table.")

    # Normalize column names to lowercase for easier SQL use
    df.columns = [col.strip().lower() for col in df.columns]

    # Rename to cleaner internal names
    rename_map = {
        "object_name": "object_name",
        "object_id": "object_id",
        "norad_cat_id": "norad_id",
        "object_type": "object_type",
        "ops_status_code": "ops_status_code",
        "owner": "owner",
        "launch_date": "launch_date",
        "launch_site": "launch_site",
        "decay_date": "decay_date",
        "period": "period_minutes",
        "inclination": "catalog_inclination_deg",
        "apogee": "apogee_km",
        "perigee": "perigee_km",
        "rcs": "rcs_m2",
        "orbit_center": "orbit_center",
        "orbit_type": "catalog_orbit_type",
    }

    df = df.rename(columns=rename_map)

    # Keep only fields we care about for now
    keep_columns = [
        "norad_id",
        "object_name",
        "object_id",
        "object_type",
        "ops_status_code",
        "owner",
        "launch_date",
        "launch_site",
        "decay_date",
        "period_minutes",
        "catalog_inclination_deg",
        "apogee_km",
        "perigee_km",
        "rcs_m2",
        "orbit_center",
        "catalog_orbit_type",
    ]

    df = df[[c for c in keep_columns if c in df.columns]]

    engine = create_engine(SQLALCHEMY_DATABASE_URI)

    logger.info("Writing %d rows to PostgreSQL table: %s", len(df), TABLE_NAME)

    df.to_sql(
        TABLE_NAME,
        con=engine,
        if_exists="replace",
        index=False,
        method="multi",
        chunksize=1000,
    )

    logger.info("Metadata load complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    store_metadata_to_sql()