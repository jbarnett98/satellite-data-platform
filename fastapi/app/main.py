import json
import os
from datetime import datetime, timezone
import logging
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sgp4.api import Satrec, jday
from skyfield.api import EarthSatellite, load, wgs84
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("SQLALCHEMY_DATABASE_URI")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not DATABASE_URL:
    raise ValueError("SQLALCHEMY_DATABASE_URI environment variable is not set")

engine = create_engine(DATABASE_URL)
ts = load.timescale()

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


def propagate_tle(line1: str, line2: str, when: datetime) -> dict | None:
    """
    Canonical propagation function.

    Returns:
    - Cartesian position directly from SGP4 (x_km, y_km, z_km)
    - Geodetic position derived for display (latitude, longitude, altitude_km)
    """
    try:
        satrec = Satrec.twoline2rv(line1, line2)

        jd, fr = jday(
            when.year,
            when.month,
            when.day,
            when.hour,
            when.minute,
            when.second + when.microsecond * 1e-6,
        )

        error_code, position_km, _velocity_km_s = satrec.sgp4(jd, fr)

        if error_code != 0:
            return None

        x_km, y_km, z_km = position_km

        satellite = EarthSatellite(line1, line2, "SAT", ts)
        t = ts.from_datetime(when)
        geocentric = satellite.at(t)
        subpoint = wgs84.subpoint(geocentric)

        latitude = float(subpoint.latitude.degrees)
        longitude = float(subpoint.longitude.degrees)
        altitude_km = float(subpoint.elevation.km)

        return {
            "timestamp": when.isoformat(),
            "x_km": float(x_km),
            "y_km": float(y_km),
            "z_km": float(z_km),
            "latitude": latitude,
            "longitude": longitude,
            "altitude_km": altitude_km,
        }

    except Exception:
        return None


@app.get("/health")
def health_check():
    start = time.perf_counter()

    response = {"status": "ok"}

    elapsed = time.perf_counter() - start
    logger.info("GET /health completed in %.3f seconds", elapsed)

    return response


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