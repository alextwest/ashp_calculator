# PostgreSQL model catalog

The calculator, metadata endpoint, and AI candidate reader use PostgreSQL when
`ASHP_DATABASE_URL` is configured. Set this in the backend deployment environment
to a PostgreSQL URL for `paradigmdatabase.postgres.database.azure.com`, including
the database name, username, and URL-encoded password. Keep credentials outside
the repository. Connections require TLS.

The app deliberately does not reuse `DATABASE_URL`, which currently identifies a
different server. Without `ASHP_DATABASE_URL`, existing Excel reads remain active.
With it configured, database errors surface instead of silently using Excel.

Install backend requirements, then run from the backend directory:

```powershell
python import_model_catalog.py
```

This imports the `indoor_combinations` worksheet from both calculated workbooks
into `ashp.model_combinations` in one transaction. Manufacturer, model, type,
source filename, and source row are explicit columns. `specifications` is a JSONB
object containing every original worksheet field, including all per-head capacity
columns. This keeps both manufacturers' worksheet layouts intact for the existing
matching engine. Database rows are read afresh for each calculation.

The importing account needs permission to create the schema/table and insert rows.
The deployed app only needs USAGE on `ashp` and SELECT on the table.
No existing table is dropped. To intentionally refresh an existing catalog:

```powershell
python import_model_catalog.py --replace
```

Both workbooks are validated before any database changes. Failed imports roll back.
The importer checks row counts before committing. A repeat import without
`--replace` fails without changing existing rows.

Example inspection queries:

```sql
SELECT manufacturer, count(*) FROM ashp.model_combinations GROUP BY manufacturer;
SELECT manufacturer, model, type,
       specifications->>'Total Capacity' AS total_capacity,
       specifications->>'BTU @ 5*F' AS heating_capacity_at_5f
FROM ashp.model_combinations;
```
