from pathlib import Path

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Data paths
DATA_DIR = BASE_DIR / "data"

RAW_DATA_PATH = DATA_DIR / "satellites_raw.txt"
CLEAN_DATA_PATH = DATA_DIR / "satellites_clean.csv"
ENRICHED_DATA_PATH = DATA_DIR / "satellites_enriched.csv"

# Logs
LOG_DIR = BASE_DIR / "logs"

# API
CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"