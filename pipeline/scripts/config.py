import os
from pathlib import Path

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Data paths
DATA_DIR = BASE_DIR / "data"

RAW_DATA_PATH = DATA_DIR / "satellites_raw.txt"
POSITION_DATA_PATH = DATA_DIR / "satellites_positions.csv"
METADATA_DATA_PATH = DATA_DIR / "satellite_metadata.csv"

# Source URLs
CELESTRAK_URL = os.environ.get(
    "CELESTRAK_URL",
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
)

CELESTRAK_SATCAT_URL = os.environ.get(
    "CELESTRAK_SATCAT_URL",
    "https://celestrak.org/satcat/records.php?GROUP=ACTIVE&FORMAT=CSV"
)

# Database
SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI")

if not SQLALCHEMY_DATABASE_URI:
    raise ValueError("SQLALCHEMY_DATABASE_URI environment variable is not set")

# AWS / S3
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")
S3_BUCKET = os.environ.get("S3_BUCKET")

if not S3_BUCKET:
    raise ValueError("S3_BUCKET environment variable is not set")

S3_LATEST_TLE_KEY = os.environ.get(
    "S3_LATEST_TLE_KEY",
    "raw/celestrak/latest/satellites.txt"
)

S3_ARCHIVE_PREFIX = os.environ.get(
    "S3_ARCHIVE_PREFIX",
    "raw/celestrak/archive/"
)

S3_FRONTEND_PREFIX = os.environ.get(
    "S3_FRONTEND_PREFIX",
    "frontend-data/"
)

if not S3_FRONTEND_PREFIX.endswith("/"):
    S3_FRONTEND_PREFIX += "/"