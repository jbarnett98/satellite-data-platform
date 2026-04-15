import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import create_engine, text

from pipeline.scripts.config import SQLALCHEMY_DATABASE_URI
from pipeline.scripts.orbital_utils import propagate_tle, tle_epoch_utc

logger = logging.getLogger(__name__)

TABLE_NAME = "satellite_trajectory_samples"
SOURCE_TABLE = "satellites_latest"
WINDOW_MINUTES = 10
STEP_SECONDS = 30


def generate_trajectory_samples(
    window_minutes: int = WINDOW_MINUTES,
    step_seconds: int = STEP_SECONDS,
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
    total_steps = int((window_minutes * 60) / step_seconds)
    total_satellites = len(rows)
    expected_total_samples = total_satellites * (total_steps + 1)
    output_rows = []

    logger.info(
        "Generating trajectory samples for %d satellites | window_minutes=%d | step_seconds=%d",
        total_satellites,
        window_minutes,
        step_seconds,
    )
    logger.info(
        "Expected sample calculations: %d satellites × %d samples each = %d total samples",
        total_satellites,
        total_steps + 1,
        expected_total_samples,
    )

    for sat_index, row in enumerate(rows, start=1):
        if sat_index == 1 or sat_index % 100 == 0:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            rate = sat_index / elapsed if elapsed > 0 else 0
            samples_done_estimate = sat_index * (total_steps + 1)

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

        for i in range(total_steps + 1):
            sample_time = start_time + timedelta(seconds=i * step_seconds)
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