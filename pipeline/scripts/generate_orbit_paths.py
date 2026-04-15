import json
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from pipeline.scripts.config import SQLALCHEMY_DATABASE_URI
from pipeline.scripts.orbital_utils import propagate_tle

logger = logging.getLogger(__name__)

TABLE_NAME = "satellite_orbit_paths"
SOURCE_TABLE = "satellites_latest"
NUM_POINTS = 90




def generate_orbit_paths(num_points: int = NUM_POINTS) -> None:
    logger.info("Connecting to database")
    engine = create_engine(SQLALCHEMY_DATABASE_URI)

    query = text(f"""
        SELECT
            satellite,
            line1,
            line2,
            norad_id,
            mean_motion_rad_per_min
        FROM {SOURCE_TABLE}
    """)

    logger.info("Reading source satellites from %s", SOURCE_TABLE)
    with engine.connect() as connection:
        rows = connection.execute(query).fetchall()

    now = datetime.now(timezone.utc)
    output_rows = []

    logger.info("Generating orbit paths for %d satellites", len(rows))

    for row in rows:
        record = dict(row._mapping)

        line1 = record.get("line1")
        line2 = record.get("line2")
        mean_motion = record.get("mean_motion_rad_per_min")

        if not line1 or not line2:
            continue

        if mean_motion is None or mean_motion == 0:
            continue

        orbital_period_minutes = float(2 * np.pi / mean_motion)
        orbital_period_seconds = orbital_period_minutes * 60
        half_period_seconds = orbital_period_seconds / 2

        points = []
        for i in range(num_points):
            fraction = i / (num_points - 1)
            offset_seconds = -half_period_seconds + (fraction * orbital_period_seconds)
            t = now + timedelta(seconds=offset_seconds)

            propagated = propagate_tle(line1, line2, t)
            if propagated is None:
                continue

            points.append(propagated)

        if not points:
            continue

        output_rows.append({
            "norad_id": int(record["norad_id"]),
            "satellite": record["satellite"],
            "orbital_period_minutes": orbital_period_minutes,
            "num_points": num_points,
            "generated_at": now.isoformat(),
            "points_json": json.dumps(points),
        })

    if not output_rows:
        raise ValueError("No orbit paths were generated")

    df = pd.DataFrame(output_rows)

    logger.info("Writing %d orbit paths to %s", len(df), TABLE_NAME)
    df.to_sql(
        TABLE_NAME,
        con=engine,
        if_exists="replace",
        index=False,
        method="multi",
        chunksize=200,
    )

    logger.info("Orbit path generation complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_orbit_paths()