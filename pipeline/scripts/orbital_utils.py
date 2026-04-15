from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sgp4.api import Satrec, jday
from skyfield.api import EarthSatellite, load, wgs84

ts = load.timescale()


def ensure_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def propagate_tle(line1: str, line2: str, when: datetime) -> dict[str, Any] | None:
    """
    Canonical propagation function for the whole project.

    Returns:
        {
            "timestamp": ISO UTC timestamp,
            "x_km": float,
            "y_km": float,
            "z_km": float,
            "latitude": float,
            "longitude": float,
            "altitude_km": float,
        }
    """
    when = ensure_utc(when)

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

        return {
            "timestamp": when.isoformat(),
            "x_km": float(x_km),
            "y_km": float(y_km),
            "z_km": float(z_km),
            "latitude": float(subpoint.latitude.degrees),
            "longitude": float(subpoint.longitude.degrees),
            "altitude_km": float(subpoint.elevation.km),
        }
    except Exception:
        return None

def tle_epoch_utc(line1: str, line2: str) -> datetime:
    satrec = Satrec.twoline2rv(line1, line2)
    year = satrec.epochyr
    year += 2000 if year < 57 else 1900

    from datetime import timedelta
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    return start + timedelta(days=satrec.epochdays - 1)