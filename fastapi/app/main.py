import json
import os
from datetime import datetime, timezone
import logging
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from app.orbital_utils import propagate_tle
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("SQLALCHEMY_DATABASE_URI")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not DATABASE_URL:
    raise ValueError("SQLALCHEMY_DATABASE_URI environment variable is not set")

engine = create_engine(DATABASE_URL)

app = FastAPI(title="Satellite API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

SATELLITES_CACHE = {
    "data": None,
    "timestamp": None,
}
SATELLITES_CACHE_TTL_SECONDS = 30

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        elapsed = time.perf_counter() - start
        logger.exception(
            "HTTP %s %s failed in %.3f seconds",
            request.method,
            request.url.path,
            elapsed,
        )
        raise

    elapsed = time.perf_counter() - start

    logger.info(
        "HTTP %s %s -> %s in %.3f seconds",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )

    return response

@app.get("/health")
def health_check():
    return {"status": "ok"}

    


@app.get("/satellites")
def get_satellites():
    total_start = time.perf_counter()

    query = text("""
        SELECT
            satellite,
            line1,
            line2,
            norad_id,
            orbit_type,
            mean_motion_rad_per_min
        FROM satellites_latest
    """)

    now = datetime.now(timezone.utc)
    cached_data = SATELLITES_CACHE["data"]
    cached_timestamp = SATELLITES_CACHE["timestamp"]

    if cached_data is not None and cached_timestamp is not None:
        age = (now - cached_timestamp).total_seconds()
        if age < SATELLITES_CACHE_TTL_SECONDS:
            logger.info("GET /satellites served from cache (age=%.1f seconds)", age)
            return cached_data

    live_rows = []

    db_start = time.perf_counter()
    with engine.connect() as connection:
        results = connection.execute(query).fetchall()
    db_elapsed = time.perf_counter() - db_start

    propagation_start = time.perf_counter()
    for row in results:
        record = dict(row._mapping)

        line1 = record.get("line1")
        line2 = record.get("line2")

        if not line1 or not line2:
            continue

        propagated = propagate_tle(line1, line2, now)
        if propagated is None:
            continue

        live_rows.append({
            "satellite": record["satellite"],
            "norad_id": record["norad_id"],
            "orbit_type": record["orbit_type"],
            "latitude": propagated["latitude"],
            "longitude": propagated["longitude"],
            "altitude_km": propagated["altitude_km"],
            "x_km": propagated["x_km"],
            "y_km": propagated["y_km"],
            "z_km": propagated["z_km"],
            "position_computed_at": propagated["timestamp"],
        })
    propagation_elapsed = time.perf_counter() - propagation_start

    total_elapsed = time.perf_counter() - total_start

    logger.info(
        "GET /satellites completed in %.3f seconds | db=%.3f | propagation=%.3f | rows_in=%d | rows_out=%d",
        total_elapsed,
        db_elapsed,
        propagation_elapsed,
        len(results),
        len(live_rows),
    )

    SATELLITES_CACHE["data"] = live_rows
    SATELLITES_CACHE["timestamp"] = now
    return live_rows


@app.get("/satellites/{norad_id}")
def get_satellite(norad_id: int):
    total_start = time.perf_counter()

    query = text("""
        SELECT
            s.satellite,
            s.line1,
            s.line2,
            s.norad_id,
            s.orbit_type,
            s.mean_motion_rad_per_min,

            m.object_name,
            m.object_id,
            m.object_type,
            m.ops_status_code,
            m.owner,
            m.launch_date,
            m.launch_site,
            m.decay_date,
            m.period_minutes,
            m.catalog_inclination_deg,
            m.apogee_km,
            m.perigee_km,
            m.rcs_m2,
            m.orbit_center,
            m.catalog_orbit_type

        FROM satellites_latest s
        LEFT JOIN satellite_metadata m
            ON s.norad_id = m.norad_id
        WHERE s.norad_id = :norad_id
        LIMIT 1
    """)

    db_start = time.perf_counter()
    with engine.connect() as connection:
        result = connection.execute(query, {"norad_id": norad_id}).fetchone()
    db_elapsed = time.perf_counter() - db_start

    if not result:
        raise HTTPException(status_code=404, detail="Satellite not found")

    record = dict(result._mapping)
    now = datetime.now(timezone.utc)

    propagation_start = time.perf_counter()
    propagated = propagate_tle(record["line1"], record["line2"], now)
    propagation_elapsed = time.perf_counter() - propagation_start

    if propagated is None:
        raise HTTPException(status_code=500, detail="Failed to propagate satellite position")

    total_elapsed = time.perf_counter() - total_start
    logger.info(
        "GET /satellites/%s completed in %.3f seconds | db=%.3f | propagation=%.3f",
        norad_id,
        total_elapsed,
        db_elapsed,
        propagation_elapsed,
    )

    return {
        "satellite": record["satellite"],
        "norad_id": record["norad_id"],
        "orbit_type": record["orbit_type"],
        "latitude": propagated["latitude"],
        "longitude": propagated["longitude"],
        "altitude_km": propagated["altitude_km"],
        "x_km": propagated["x_km"],
        "y_km": propagated["y_km"],
        "z_km": propagated["z_km"],
        "position_computed_at": propagated["timestamp"],
        "object_name": record.get("object_name"),
        "object_id": record.get("object_id"),
        "object_type": record.get("object_type"),
        "ops_status_code": record.get("ops_status_code"),
        "owner": record.get("owner"),
        "launch_date": record.get("launch_date"),
        "launch_site": record.get("launch_site"),
        "decay_date": record.get("decay_date"),
        "period_minutes": record.get("period_minutes"),
        "catalog_inclination_deg": record.get("catalog_inclination_deg"),
        "apogee_km": record.get("apogee_km"),
        "perigee_km": record.get("perigee_km"),
        "rcs_m2": record.get("rcs_m2"),
        "orbit_center": record.get("orbit_center"),
        "catalog_orbit_type": record.get("catalog_orbit_type"),
    }


@app.get("/satellites/{norad_id}/orbit-path")
def get_orbit_path(norad_id: int):
    query = text("""
        SELECT
            norad_id,
            satellite,
            orbital_period_minutes,
            points_json
        FROM satellite_orbit_paths
        WHERE norad_id = :norad_id
        LIMIT 1
    """)

    with engine.connect() as connection:
        row = connection.execute(query, {"norad_id": norad_id}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Orbit path not found")

    record = dict(row._mapping)

    return {
        "norad_id": record["norad_id"],
        "satellite": record["satellite"],
        "orbital_period_minutes": record["orbital_period_minutes"],
        "path_source": "precomputed",
        "points": json.loads(record["points_json"]),
    }






@app.get("/satellite-trajectories")
def get_satellite_trajectories():
    total_start = time.perf_counter()

    latest_batch_query = text("""
        SELECT MAX(generated_at) AS latest_generated_at
        FROM satellite_trajectory_samples
    """)

    db_start = time.perf_counter()
    with engine.connect() as connection:
        latest_batch_row = connection.execute(latest_batch_query).fetchone()
    db_elapsed = time.perf_counter() - db_start

    latest_generated_at = (
        latest_batch_row.latest_generated_at
        if latest_batch_row and latest_batch_row.latest_generated_at is not None
        else None
    )

    if latest_generated_at is None:
        logger.warning("GET /satellite-trajectories returned no rows: no generated batch found")
        return {
            "generated_at": None,
            "window_minutes": None,
            "step_seconds": None,
            "satellites": [],
        }

    query = text("""
        SELECT
            norad_id,
            sample_time,
            x_km,
            y_km,
            z_km,
            generated_at
        FROM satellite_trajectory_samples
        WHERE generated_at = :latest_generated_at
        ORDER BY norad_id, sample_time
    """)

    with engine.connect() as connection:
        results = connection.execute(
            query,
            {"latest_generated_at": latest_generated_at},
        ).fetchall()

    if not results:
        logger.warning(
            "GET /satellite-trajectories returned no rows for latest batch %s",
            latest_generated_at,
        )
        return {
            "generated_at": latest_generated_at.isoformat(),
            "window_minutes": None,
            "step_seconds": None,
            "satellites": [],
        }

    satellites = []
    current_norad_id = None
    current_samples = []

    for row in results:
        record = dict(row._mapping)

        norad_id = int(record["norad_id"])
        sample = [
            record["sample_time"].isoformat(),
            float(record["x_km"]),
            float(record["y_km"]),
            float(record["z_km"]),
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

    total_elapsed = time.perf_counter() - total_start
    logger.info(
        "GET /satellite-trajectories completed in %.3f seconds | db=%.3f | satellites=%d | rows=%d | generated_at=%s",
        total_elapsed,
        db_elapsed,
        len(satellites),
        len(results),
        latest_generated_at.isoformat(),
    )

    return {
        "generated_at": latest_generated_at.isoformat(),
        "window_minutes": 10,
        "step_seconds": 30,
        "satellites": satellites,
    }