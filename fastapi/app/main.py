import os
from datetime import datetime, timedelta, timezone

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sgp4.api import Satrec, jday
from skyfield.api import EarthSatellite, load, wgs84
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("SQLALCHEMY_DATABASE_URI")

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


def propagate_tle(line1: str, line2: str, when: datetime) -> dict | None:
    """
    Canonical propagation function.

    Returns:
    - Cartesian position directly from SGP4 (x_km, y_km, z_km)
    - Geodetic position derived for display (latitude, longitude, altitude_km)

    This function is the single orbital source of truth for:
    - /satellites
    - /satellites/{norad_id}
    - /satellites/{norad_id}/orbit-path
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

        # Use Skyfield for geodetic display conversion from the same TLE/time
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
    return {"status": "ok"}


@app.get("/satellites")
def get_satellites():
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
    live_rows = []

    with engine.connect() as connection:
        results = connection.execute(query).fetchall()

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
            "line1": line1,
            "line2": line2,
            "norad_id": record["norad_id"],
            "orbit_type": record["orbit_type"],
            "mean_motion_rad_per_min": record["mean_motion_rad_per_min"],
            "latitude": propagated["latitude"],
            "longitude": propagated["longitude"],
            "altitude_km": propagated["altitude_km"],
            "x_km": propagated["x_km"],
            "y_km": propagated["y_km"],
            "z_km": propagated["z_km"],
            "position_computed_at": propagated["timestamp"],
        })

    return live_rows


@app.get("/satellites/{norad_id}")
def get_satellite(norad_id: int):
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

    with engine.connect() as connection:
        result = connection.execute(query, {"norad_id": norad_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Satellite not found")

    record = dict(result._mapping)
    now = datetime.now(timezone.utc)

    propagated = propagate_tle(record["line1"], record["line2"], now)
    if propagated is None:
        raise HTTPException(status_code=500, detail="Failed to propagate satellite position")

    return {
        "satellite": record["satellite"],
        "line1": record["line1"],
        "line2": record["line2"],
        "norad_id": record["norad_id"],
        "orbit_type": record["orbit_type"],
        "mean_motion_rad_per_min": record["mean_motion_rad_per_min"],

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
def get_orbit_path(norad_id: int, step_seconds: int = 10):
    query = text("""
        SELECT
            satellite,
            line1,
            line2,
            norad_id,
            mean_motion_rad_per_min
        FROM satellites_latest
        WHERE norad_id = :norad_id
        LIMIT 1
    """)

    with engine.connect() as connection:
        row = connection.execute(query, {"norad_id": norad_id}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Satellite not found")

    record = dict(row._mapping)

    mean_motion = record["mean_motion_rad_per_min"]
    if mean_motion is None or mean_motion == 0:
        raise HTTPException(status_code=400, detail="Invalid mean motion for orbit path")

    orbital_period_minutes = float(2 * np.pi / mean_motion)
    half_period_seconds = int((orbital_period_minutes * 60) / 2)

    now = datetime.now(timezone.utc)
    points = []

    for offset in range(-half_period_seconds, half_period_seconds + 1, step_seconds):
        t = now + timedelta(seconds=offset)

        propagated = propagate_tle(record["line1"], record["line2"], t)
        if propagated is None:
            continue

        points.append(propagated)

    if not points:
        raise HTTPException(status_code=500, detail="Failed to generate orbit path")

    current_position = propagate_tle(record["line1"], record["line2"], now)
    if current_position is None:
        raise HTTPException(status_code=500, detail="Failed to propagate current position")

    return {
        "norad_id": record["norad_id"],
        "satellite": record["satellite"],
        "orbital_period_minutes": orbital_period_minutes,
        "current_position": current_position,
        "points": points,
    }