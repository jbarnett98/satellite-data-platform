import logging

import pandas as pd
from sqlalchemy import create_engine

from pipeline.scripts.config import POSITION_DATA_PATH, SQLALCHEMY_DATABASE_URI

logger = logging.getLogger(__name__)

TABLE_NAME = "satellites_latest"


def store_to_sql() -> None:
    logger.info("Loading processed satellite data from %s", POSITION_DATA_PATH)

    df = pd.read_csv(POSITION_DATA_PATH)

    if df.empty:
        raise ValueError("Processed satellite dataset is empty. Refusing to load empty table.")

    logger.info("Loaded %d rows from processed CSV", len(df))

    engine = create_engine(SQLALCHEMY_DATABASE_URI)

    logger.info("Writing data to PostgreSQL table: %s", TABLE_NAME)

    df.to_sql(
        TABLE_NAME,
        con=engine,
        if_exists="replace",
        index=False,
        method="multi",
        chunksize=1000,
    )

    logger.info("Load complete: %d rows written to %s", len(df), TABLE_NAME)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    store_to_sql()