import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sgp4.api import Satrec, jday

from pipeline.scripts.config import RAW_DATA_PATH, POSITION_DATA_PATH

logger = logging.getLogger(__name__)


def is_line1(line: str) -> bool:
    return line.startswith("1 ")


def is_line2(line: str) -> bool:
    return line.startswith("2 ")


def parse_tle_records(lines: List[str]) -> List[Dict]:
    """
    Parse raw TLE lines into structured satellite records.

    Supports:
    - 3-line format: name, line1, line2
    - 2-line format: line1, line2

    Ignores blank lines and skips malformed records safely.
    """
    satellites = []

    current_name: Optional[str] = None
    current_line1: Optional[str] = None

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            continue

        if is_line1(line):
            if current_line1 is not None:
                logger.warning(
                    "Dropping incomplete record before new line1: name=%r line1=%r",
                    current_name,
                    current_line1,
                )
            current_line1 = line

        elif is_line2(line):
            if current_line1 is None:
                logger.warning("Found line2 without preceding line1: %r", line)
                current_name = None
                continue

            try:
                sat = Satrec.twoline2rv(current_line1, line)

                satellites.append({
                    "satellite": current_name if current_name else f"UNKNOWN_{sat.satnum}",
                    "line1": current_line1,
                    "line2": line,
                    "norad_id": int(sat.satnum),
                    "inclination_rad": float(sat.inclo),
                    "eccentricity": float(sat.ecco),
                    "mean_motion_rad_per_min": float(sat.no_kozai),
                    "right_ascension_rad": float(sat.nodeo),
                    "perigee_rad": float(sat.argpo),
                    "mean_anomaly_rad": float(sat.mo),
                })

            except Exception as e:
                logger.exception(
                    "Failed to parse record: name=%r line1=%r line2=%r error=%s",
                    current_name,
                    current_line1,
                    line,
                    e,
                )

            current_name = None
            current_line1 = None

        else:
            if current_line1 is not None:
                logger.warning(
                    "Found name-like line while waiting for line2. "
                    "Dropping incomplete record: name=%r line1=%r",
                    current_name,
                    current_line1,
                )
                current_line1 = None

            current_name = line

    if current_line1 is not None:
        logger.warning(
            "Input ended with incomplete record: name=%r line1=%r",
            current_name,
            current_line1,
        )

    return satellites


def load_and_parse_raw_tle() -> pd.DataFrame:
    logger.info("Loading raw TLE data from %s", RAW_DATA_PATH)

    with open(RAW_DATA_PATH, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    logger.info("Raw file contains %d total lines", len(lines))

    preview_count = min(12, len(lines))
    logger.info("First %d raw lines:\n%s", preview_count, "".join(lines[:preview_count]))

    satellites = parse_tle_records(lines)
    df = pd.DataFrame(satellites)

    logger.info("Parsed %d valid satellite records", len(df))
    return df


def enrich_satellite_data(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Enriching satellite data")

    df = df.copy()

    df["orbital_period_minutes"] = 2 * np.pi / df["mean_motion_rad_per_min"]

    def classify_orbit(period: float) -> str:
        if period < 128:
            return "LEO"
        elif period < 1430:
            return "MEO"
        return "GEO"

    df["orbit_type"] = df["orbital_period_minutes"].apply(classify_orbit)

    return df


def compute_positions(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Computing current satellite positions")

    df = df.copy()

    latitudes = []
    longitudes = []
    altitudes = []
    xs = []
    ys = []
    zs = []

    now = datetime.now(timezone.utc)
    jd, fr = jday(
        now.year,
        now.month,
        now.day,
        now.hour,
        now.minute,
        now.second + now.microsecond * 1e-6,
    )

    for _, row in df.iterrows():
        try:
            sat = Satrec.twoline2rv(row["line1"], row["line2"])
            error_code, position_km, _velocity_km_s = sat.sgp4(jd, fr)

            if error_code == 0:
                x_km, y_km, z_km = position_km

                lat_deg = np.degrees(np.arctan2(z_km, np.sqrt(x_km**2 + y_km**2)))
                lon_deg = np.degrees(np.arctan2(y_km, x_km))
                altitude_km = np.sqrt(x_km**2 + y_km**2 + z_km**2) - 6371.0

                latitudes.append(float(lat_deg))
                longitudes.append(float(lon_deg))
                altitudes.append(float(altitude_km))

                radius_km = 6371.0 + altitude_km
                xs.append(float(radius_km * np.cos(np.radians(lat_deg)) * np.cos(np.radians(lon_deg))))
                ys.append(float(radius_km * np.cos(np.radians(lat_deg)) * np.sin(np.radians(lon_deg))))
                zs.append(float(radius_km * np.sin(np.radians(lat_deg))))
            else:
                latitudes.append(None)
                longitudes.append(None)
                altitudes.append(None)
                xs.append(None)
                ys.append(None)
                zs.append(None)

        except Exception as e:
            logger.warning("Failed position calculation for %r: %s", row.get("satellite"), e)
            latitudes.append(None)
            longitudes.append(None)
            altitudes.append(None)
            xs.append(None)
            ys.append(None)
            zs.append(None)

    df["latitude"] = latitudes
    df["longitude"] = longitudes
    df["altitude_km"] = altitudes
    df["x"] = xs
    df["y"] = ys
    df["z"] = zs
    df["position_computed_at"] = now.isoformat()

    return df


def process_satellite_data() -> pd.DataFrame:
    logger.info("Starting satellite processing pipeline")

    df = load_and_parse_raw_tle()
    df = enrich_satellite_data(df)
    df = compute_positions(df)

    POSITION_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(POSITION_DATA_PATH, index=False)

    logger.info("Wrote %d processed satellite records to %s", len(df), POSITION_DATA_PATH)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    process_satellite_data()