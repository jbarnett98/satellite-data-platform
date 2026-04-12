import logging
from pipeline.scripts.config import LOG_DIR

from pathlib import Path

def setup_logger():
    log_dir = LOG_DIR
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "pipeline.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger()