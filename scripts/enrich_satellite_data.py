import pandas as pd
import logging
from config import CLEAN_DATA_PATH, ENRICHED_DATA_PATH

logger = logging.getLogger(__name__)

def enrich_satellite_data():

    logger.info("Calculating")

    df = pd.read_csv(CLEAN_DATA_PATH)

    # Orbital period
    df["orbital_period_minutes"] = 1440 / df["mean_motion"]

    # Orbit classification
    def classify_orbit(period):
        if period < 130:
            return "LEO"
        elif period < 1000:
            return "MEO"
        else:
            return "GEO"

    df["orbit_type"] = df["orbital_period_minutes"].apply(classify_orbit)

    df.to_csv(ENRICHED_DATA_PATH, index=False)

    logger.info("Satellite dataset enriched")