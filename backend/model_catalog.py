"""Shared PostgreSQL model catalog; preserves every original workbook field."""
import os
from urllib.parse import urlparse, unquote

import pandas as pd


def database_enabled():
    return bool(os.getenv("ASHP_DATABASE_URL"))


def connect():
    import psycopg
    url = urlparse(os.environ["ASHP_DATABASE_URL"])
    if url.scheme not in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        raise ValueError("ASHP_DATABASE_URL must be a PostgreSQL URL")
    return psycopg.connect(
        host=url.hostname, port=url.port or 5432,
        dbname=unquote(url.path.lstrip("/")), user=unquote(url.username or ""),
        password=unquote(url.password or ""), sslmode="require", connect_timeout=10,
    )


def read_models(manufacturer):
    with connect() as conn:
        rows = conn.execute(
            "SELECT specifications FROM ashp.model_combinations "
            "WHERE manufacturer = %s ORDER BY source_row", (manufacturer,),
        ).fetchall()
    if not rows:
        raise ValueError(f"No database model combinations found for {manufacturer}; run import_model_catalog.py")
    return pd.DataFrame([row[0] for row in rows])
