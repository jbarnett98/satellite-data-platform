import os
from pathlib import Path

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Data paths
DATA_DIR = BASE_DIR / "data"

RAW_DATA_PATH = DATA_DIR / "satellites_raw.txt"
POSITION_DATA_PATH = DATA_DIR / "satellites_positions.csv"

# Source
CELESTRAK_URL = os.environ.get(
    "CELESTRAK_URL",
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
)

METADATA_DATA_PATH = DATA_DIR / "satellite_metadata.csv"

CELESTRAK_SATCAT_URL = (
    "https://celestrak.org/satcat/records.php?GROUP=ACTIVE&FORMAT=CSV"
)



# Database
SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI")



if not SQLALCHEMY_DATABASE_URI:
    raise ValueError("SQLALCHEMY_DATABASE_URI environment variable is not set")