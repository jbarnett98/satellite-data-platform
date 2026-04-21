import json
import logging
from datetime import timedelta

from sqlalchemy import create_engine, text

from pipeline.scripts.config import (
    SQLALCHEMY_DATABASE_URI,
    S3_FRONTEND_PREFIX,
)
from pipeline.scripts.generate_trajectory_samples import (
    WINDOW_MINUTES as TRAJECTORY_WINDOW_MINUTES,
    NUM_POINTS as TRAJECTORY_NUM_POINTS,
)
from pipeline.scripts.s3_utils import upload_json_object

logger = logging.getLogger(__name__)

engine = create_engine(SQLALCHEMY_DATABASE_URI)


def _s3_key(relative_path: str) -> str:
    return f"{S3_FRONTEND_PREFIX}{relative_path.lstrip('/')}"


def _json_date(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def export_satellites_json() -> None:
    """
    Export a lightweight initial satellite payload for the frontend.

    We seed this from the latest trajectory batch, taking the first sample
    per satellite so the frontend has an initial position without needing
    live propagation from the API.
    """
    query = text("""
        WITH latest_batch AS (
            SELECT MAX(generated_at) AS latest_generated_at
            FROM satellite_trajectory_samples
        ),
        ranked_samples AS (
            SELECT
                t.norad_id,
                t.sample_time,
                t.x_km,
                t.y_km,
                t.z_km,
                t.altitude_km,
                ROW_NUMBER() OVER (
                    PARTITION BY t.norad_id
                    ORDER BY t.sample_time
                ) AS rn
            FROM satellite_trajectory_samples t
            JOIN latest_batch lb
                ON t.generated_at = lb.latest_generated_at
        )
        SELECT
            s.satellite,
            s.norad_id,
            s.orbit_type,
            rs.x_km,
            rs.y_km,
            rs.z_km,
            rs.altitude_km,
            rs.sample_time AS position_computed_at,

            m.object_name,
            m.object_id,
            m.object_type,
            m.owner,
            m.launch_date,
            m.launch_site,
            m.apogee_km,
            m.perigee_km,
            m.catalog_inclination_deg

        FROM satellites_latest s
        JOIN ranked_samples rs
            ON s.norad_id = rs.norad_id
        LEFT JOIN satellite_metadata m
            ON s.norad_id = m.norad_id
        WHERE rs.rn = 1
        ORDER BY s.norad_id
    """)

    with engine.connect() as connection:
        rows = connection.execute(query).fetchall()

    payload = []
    for row in rows:
        record = dict(row._mapping)
        payload.append({
            "satellite": record["satellite"],
            "norad_id": int(record["norad_id"]),
            "orbit_type": record["orbit_type"],
            "x_km": round(float(record["x_km"]), 1),
            "y_km": round(float(record["y_km"]), 1),
            "z_km": round(float(record["z_km"]), 1),
            "altitude_km": round(float(record["altitude_km"]), 1) if record["altitude_km"] is not None else None,
            "position_computed_at": _json_date(record.get("position_computed_at")),

            "object_name": record.get("object_name"),
            "object_id": record.get("object_id"),
            "object_type": record.get("object_type"),
            "owner": record.get("owner"),
            "launch_date": _json_date(record.get("launch_date")),
            "launch_site": record.get("launch_site"),
            "apogee_km": float(record["apogee_km"]) if record.get("apogee_km") is not None else None,
            "perigee_km": float(record["perigee_km"]) if record.get("perigee_km") is not None else None,
            "catalog_inclination_deg": float(record["catalog_inclination_deg"]) if record.get("catalog_inclination_deg") is not None else None,
        })

    upload_json_object(_s3_key("latest/satellites.json"), payload)
    logger.info("Exported satellites.json with %d rows", len(payload))


def export_trajectories_json(window_minutes: int = 30, stride: int = 1) -> None:
    """
    Export the bulk trajectory payload in the same shape as the current API,
    but as a static JSON artifact in S3.
    """
    if window_minutes <= 0:
        raise ValueError("window_minutes must be > 0")

    if stride <= 0:
        raise ValueError("stride must be > 0")

    latest_batch_query = text("""
        SELECT MAX(generated_at) AS latest_generated_at
        FROM satellite_trajectory_samples
    """)

    with engine.connect() as connection:
        latest_batch_row = connection.execute(latest_batch_query).fetchone()

    latest_generated_at = (
        latest_batch_row.latest_generated_at
        if latest_batch_row and latest_batch_row.latest_generated_at is not None
        else None
    )

    if latest_generated_at is None:
        payload = {
            "generated_at": None,
            "window_minutes": None,
            "num_points": None,
            "step_seconds": None,
            "stride": stride,
            "satellites": [],
        }
        upload_json_object(_s3_key("latest/trajectories.json"), payload)
        logger.warning("No trajectory batch found; exported empty trajectories.json")
        return

    window_end = latest_generated_at + timedelta(minutes=window_minutes)

    query = text("""
        WITH ranked_samples AS (
            SELECT
                norad_id,
                sample_time,
                x_km,
                y_km,
                z_km,
                generated_at,
                ROW_NUMBER() OVER (
                    PARTITION BY norad_id
                    ORDER BY sample_time
                ) - 1 AS sample_index
            FROM satellite_trajectory_samples
            WHERE generated_at = :latest_generated_at
              AND sample_time <= :window_end
        )
        SELECT
            norad_id,
            x_km,
            y_km,
            z_km,
            sample_index
        FROM ranked_samples
        WHERE MOD(sample_index, :stride) = 0
        ORDER BY norad_id, sample_index
    """)

    with engine.connect() as connection:
        results = connection.execute(
            query,
            {
                "latest_generated_at": latest_generated_at,
                "window_end": window_end,
                "stride": stride,
            },
        ).fetchall()

    satellites = []
    current_norad_id = None
    current_samples = []

    for row in results:
        record = dict(row._mapping)

        norad_id = int(record["norad_id"])
        sample = [
            round(float(record["x_km"]), 1),
            round(float(record["y_km"]), 1),
            round(float(record["z_km"]), 1),
        ]

        if current_norad_id is None:
            current_norad_id = norad_id

        if norad_id != current_norad_id:
            satellites.append({
                "norad_id": current_norad_id,
                "samples": current_samples,
            })
            current_norad_id = norad_id
            current_samples = []

        current_samples.append(sample)

    if current_norad_id is not None:
        satellites.append({
            "norad_id": current_norad_id,
            "samples": current_samples,
        })

    payload = {
        "generated_at": latest_generated_at.isoformat(),
        "window_minutes": window_minutes,
        "num_points": TRAJECTORY_NUM_POINTS,
        "step_seconds": (TRAJECTORY_WINDOW_MINUTES * 60) / (TRAJECTORY_NUM_POINTS - 1),
        "stride": stride,
        "satellites": satellites,
    }

    upload_json_object(_s3_key("latest/trajectories.json"), payload)
    logger.info("Exported trajectories.json with %d satellites", len(satellites))


def export_orbit_paths_json(chunk_size: int = 100) -> None:
    """
    Export orbit paths in chunked files instead of one file per NORAD ID.
    Also writes an index so the frontend can locate the right chunk.

    Each point is compacted to:
    [timestamp, x_km, y_km, z_km]
    to reduce payload size substantially.
    """
    query = text("""
        SELECT
            norad_id,
            satellite,
            orbital_period_minutes,
            points_json
        FROM satellite_orbit_paths
        ORDER BY norad_id
    """)

    with engine.connect() as connection:
        rows = connection.execute(query).fetchall()

    if not rows:
        logger.warning("No orbit paths found to export")
        return

    chunk_payloads = {}
    index_payload = {}

    for idx, row in enumerate(rows):
        record = dict(row._mapping)
        norad_id = int(record["norad_id"])

        raw_points = json.loads(record["points_json"])
        compact_points = []

        for point in raw_points:
            if (
                point.get("timestamp") is None or
                point.get("x_km") is None or
                point.get("y_km") is None or
                point.get("z_km") is None
            ):
                continue

            compact_points.append([
                point["timestamp"],
                round(float(point["x_km"]), 1),
                round(float(point["y_km"]), 1),
                round(float(point["z_km"]), 1),
            ])

        chunk_number = idx // chunk_size
        chunk_key = f"orbit-paths/chunks/chunk-{chunk_number:04d}.json"

        if chunk_key not in chunk_payloads:
            chunk_payloads[chunk_key] = {}

        chunk_payloads[chunk_key][str(norad_id)] = {
            "norad_id": norad_id,
            "satellite": record["satellite"],
            "orbital_period_minutes": float(record["orbital_period_minutes"]),
            "path_source": "precomputed",
            "points": compact_points,
        }

        index_payload[str(norad_id)] = chunk_key

    for idx, (chunk_key, payload) in enumerate(chunk_payloads.items(), start=1):
        upload_json_object(_s3_key(chunk_key), payload, log_upload=False)

        if idx == 1 or idx % 10 == 0:
            logger.info(
                "Uploaded orbit path chunk %d/%d",
                idx,
                len(chunk_payloads),
            )

    upload_json_object(_s3_key("orbit-paths/index.json"), index_payload, log_upload=True)

    logger.info(
        "Exported orbit path chunks: %d chunks covering %d satellites",
        len(chunk_payloads),
        len(index_payload),
    )


def export_frontend_artifacts() -> None:
    logger.info("Exporting frontend artifacts")
    export_satellites_json()
    export_trajectories_json(window_minutes=30, stride=1)
    export_orbit_paths_json(chunk_size=100)
    logger.info("Frontend artifact export complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    export_frontend_artifacts()