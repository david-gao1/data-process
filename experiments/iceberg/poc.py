"""Isolated real Iceberg snapshot interoperability experiment; synthetic data only."""
import json
from pathlib import Path
import tempfile
import time

import duckdb
import pyarrow as pa
from pyiceberg.catalog import load_catalog

start = time.monotonic()
with tempfile.TemporaryDirectory(prefix="dp-iceberg-") as directory:
    root = Path(directory)
    catalog = load_catalog("local", type="sql", uri=f"sqlite:///{root / 'catalog.db'}",
                           warehouse=f"file://{root / 'warehouse'}")
    catalog.create_namespace("demo")
    schema = pa.schema([pa.field("business_date", pa.string()), pa.field("province", pa.string()), pa.field("active_users", pa.int64())])
    table = catalog.create_table("demo.daily_active", schema=schema)
    def data(count):
        return pa.Table.from_pylist([{"business_date": "2026-10-14", "province": "北京", "active_users": count}], schema=schema)
    table.append(data(3))
    first = table.current_snapshot().snapshot_id
    table.overwrite(data(4))
    second = table.current_snapshot().snapshot_id
    assert first != second
    old = table.scan(snapshot_id=first).to_arrow().to_pylist()
    current = table.scan(snapshot_id=second).to_arrow().to_pylist()
    assert old[0]["active_users"] == 3 and current[0]["active_users"] == 4
    # This is an Arrow in-memory bridge, not DuckDB's native Iceberg extension.
    con = duckdb.connect()
    con.register("snapshot_data", table.scan(snapshot_id=first).to_arrow())
    assert con.execute("SELECT SUM(active_users) FROM snapshot_data").fetchone()[0] == 3
    # Reopen catalog to prove persistence; no Docker or Spark.
    reopened = load_catalog("local", type="sql", uri=f"sqlite:///{root / 'catalog.db'}")
    assert reopened.load_table("demo.daily_active").current_snapshot().snapshot_id == second
    print(json.dumps({"passed": True, "first_snapshot": first, "second_snapshot": second,
                      "historical_rows": old, "current_rows": current,
                      "duckdb": duckdb.__version__, "bridge": "in-memory Arrow",
                      "catalog_reopen": True, "seconds": round(time.monotonic() - start, 3)}, ensure_ascii=False, indent=2))
