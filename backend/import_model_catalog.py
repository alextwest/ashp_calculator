"""Import both model workbooks atomically. Existing catalog requires --replace."""
import argparse
import json

import pandas as pd
from psycopg.types.json import Jsonb

from model_catalog import connect
from ashp_calculator_logic import MANUFACTURER_FILES, SHEET_NAME, detect_unit_columns


def read_workbooks():
    records = []
    for manufacturer, path in MANUFACTURER_FILES.items():
        frame = pd.read_excel(path, sheet_name=SHEET_NAME)
        detect_unit_columns(frame)
        required = {"Model", "Type", "Indoor Capacity", "Total Capacity"}
        if not required.issubset(frame.columns) or frame.empty:
            raise ValueError(f"Invalid or empty workbook: {path.name}")
        # pandas converts missing cells to JSON null, preserving all column names.
        rows = json.loads(frame.to_json(orient="records", double_precision=15))
        for index, row in enumerate(rows, start=2):
            records.append((manufacturer, index, path.name, str(row["Model"]),
                            row.get("Type"), Jsonb(row)))
        print(f"Validated {manufacturer}: {len(rows)} rows")
    return records


def import_catalog(replace=False):
    records = read_workbooks()
    with connect() as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS ashp")
        conn.execute("""CREATE TABLE IF NOT EXISTS ashp.model_combinations (
            manufacturer text NOT NULL CHECK (manufacturer IN ('Fujitsu', 'LG')),
            source_row integer NOT NULL,
            source_file text NOT NULL,
            model text NOT NULL,
            type text,
            specifications jsonb NOT NULL,
            imported_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (manufacturer, source_row)
        )""")
        conn.execute("LOCK TABLE ashp.model_combinations IN EXCLUSIVE MODE")
        if conn.execute("SELECT EXISTS (SELECT 1 FROM ashp.model_combinations)").fetchone()[0]:
            if not replace:
                raise ValueError("Catalog already populated. Use --replace to refresh both manufacturers atomically.")
            conn.execute("DELETE FROM ashp.model_combinations WHERE manufacturer IN ('Fujitsu', 'LG')")
        with conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO ashp.model_combinations "
                "(manufacturer, source_row, source_file, model, type, specifications) VALUES (%s,%s,%s,%s,%s,%s)",
                records,
            )
        counts = conn.execute("SELECT manufacturer, count(*) FROM ashp.model_combinations GROUP BY manufacturer").fetchall()
        expected = {m: sum(r[0] == m for r in records) for m in MANUFACTURER_FILES}
        if dict(counts) != expected:
            raise ValueError("Imported row counts did not match workbooks; rolling back")
    print(f"Import committed: {dict(counts)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true")
    import_catalog(parser.parse_args().replace)
