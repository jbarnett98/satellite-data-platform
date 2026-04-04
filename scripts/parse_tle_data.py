from pathlib import Path
import pandas as pd
import logging
from config import RAW_DATA_PATH, CLEAN_DATA_PATH

logger = logging.getLogger(__name__)

def parse_tle_data():

    logger.info("Parsing TLE dataset")
    
    file_path = RAW_DATA_PATH

    with open(file_path) as f:
        lines = f.readlines()

    satellites = []

    for i in range(0,len(lines),6):
        name = lines[i].strip()
        line1 = lines[i+2].split()
        line2 = lines[i+4].split()


        
        designator = float(line2[1])
        inclination = float(line2[2])
        right_ascension = float(line2[3])
        eccentricity = float(('0.'+line2[4]))
        perigee = float(line2[5])
        mean_anomaly = float(line2[6])
        mean_motion = float(line2[7])

        satellites.append({
            "satellite":name,
            "norad_id":designator,
            "inclination":inclination,
            "eccentricity":eccentricity,
            "mean_motion":mean_motion,
            "right ascension":right_ascension,
            "perigee":perigee,
            "mean anomaly": mean_anomaly
        })

    df = pd.DataFrame(satellites)
    df.to_csv(CLEAN_DATA_PATH.csv, index=False)

    logger.info(f"Parsed {len(df)} satellites")

if __name__ == "__main__":
    parse_tle_data()