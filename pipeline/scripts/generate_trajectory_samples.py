import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import create_engine, text

from pipeline.scripts.config import SQLALCHEMY_DATABASE_URI
from pipeline.scripts.orbital_utils import propagate_tle, tle_epoch_utc

logger = logging.getLogger(__name__)

TABLE_NAME = "satellite_trajectory_samples"
SOURCE_TABLE = "satellites_latest"
WINDOW_MINUTES = 180
NUM_POINTS = 90


def generate_trajectory_samples(
    window_minutes: int = WINDOW_MINUTES,
    num_points: int = NUM_POINTS,
) -> None:
    logger.info("Connecting to database")
    engine = create_engine(SQLALCHEMY_DATABASE_URI)

    query = text(f"""
        SELECT
            satellite,
            line1,
            line2,
            norad_id
        FROM {SOURCE_TABLE}
    """)

    logger.info("Reading source satellites from %s", SOURCE_TABLE)
    with engine.connect() as connection:
        rows = connection.execute(query).fetchall()

    start_time = datetime.now(timezone.utc)
    window_seconds = window_minutes * 60
    step_seconds = window_seconds / (num_points - 1)
    total_satellites = len(rows)
    expected_total_samples = total_satellites * num_points
    output_rows = []

    logger.info(
        "Generating trajectory samples for %d satellites | window_minutes=%d | num_points=%d | step_seconds=%.2f",
        total_satellites,
        window_minutes,
        num_points,
        step_seconds,
    )
    logger.info(
        "Expected sample calculations: %d satellites × %d samples each = %d total samples",
        total_satellites,
        num_points,
        expected_total_samples,
    )

    for sat_index, row in enumerate(rows, start=1):
        if sat_index == 1 or sat_index % 100 == 0:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            rate = sat_index / elapsed if elapsed > 0 else 0
            samples_done_estimate = sat_index * num_points

            logger.info(
                "Trajectory progress: %d/%d satellites | est_samples=%d/%d | %.2f sat/sec | rows_so_far=%d",
                sat_index,
                total_satellites,
                samples_done_estimate,
                expected_total_samples,
                rate,
                len(output_rows),
            )

        record = dict(row._mapping)

        line1 = record.get("line1")
        line2 = record.get("line2")
        norad_id = record.get("norad_id")

        if not line1 or not line2 or norad_id is None:
            continue

        try:
            source_tle_epoch = tle_epoch_utc(line1, line2)
        except Exception:
            source_tle_epoch = None

        for i in range(num_points):
            offset_seconds = i * step_seconds
            sample_time = start_time + timedelta(seconds=offset_seconds)
            propagated = propagate_tle(line1, line2, sample_time)

            if propagated is None:
                continue

            output_rows.append({
                "norad_id": int(norad_id),
                "sample_time": sample_time,
                "x_km": propagated["x_km"],
                "y_km": propagated["y_km"],
                "z_km": propagated["z_km"],
                "latitude": propagated["latitude"],
                "longitude": propagated["longitude"],
                "altitude_km": propagated["altitude_km"],
                "generated_at": start_time,
                "source_tle_epoch": source_tle_epoch,
            })

    if not output_rows:
        raise ValueError("No trajectory samples were generated")

    df = pd.DataFrame(output_rows)

    logger.info("Writing %d trajectory rows to %s", len(df), TABLE_NAME)
    df.to_sql(
        TABLE_NAME,
        con=engine,
        if_exists="replace",
        index=False,
        method="multi",
        chunksize=2000,
    )

    logger.info("Trajectory sample generation complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_trajectory_samples()