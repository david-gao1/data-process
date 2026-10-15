"""Release-snapshotted calculator. No delivery/control database writes."""
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

import duckdb

PROVINCES = {"北京", "上海", "广东"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def durable(path):
    with Path(path).open("rb") as stream:
        os.fsync(stream.fileno())


def calculate(spec):
    source, output = Path(spec["source"]), Path(spec["output"])
    if digest(source) != spec["source_hash"]:
        raise ValueError("source checksum mismatch")
    expected = {p: set() for p in PROVINCES}
    with source.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["business_date", "user_id", "province"]:
            raise ValueError("invalid source schema")
        for row in reader:
            if (None in row or row["business_date"] != spec["date"]
                    or not row["user_id"] or not row["user_id"].strip()
                    or row["province"] not in PROVINCES):
                raise ValueError("invalid source row: date/user/province")
            expected[row["province"]].add(row["user_id"])
    if not all(expected.values()):
        raise ValueError("data not ready: missing province or empty partition")
    print("input contract and readiness passed", flush=True)
    # Delay is an explicit test-only fault injection stored in the run specification.
    time.sleep(spec["delay"])
    with duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as con:
        con.execute("CREATE TABLE events AS SELECT * FROM read_csv(?, all_varchar=true)", [str(source)])
        con.execute("SET enable_external_access=false")
        sql = Path(spec["sql"]).read_text()
        result = con.execute(sql, {"business_date": spec["date"]})
        if [d[0] for d in result.description] != ["business_date", "province", "active_users"]:
            raise ValueError("invalid output schema")
        rows = result.fetchall()
    oracle = sorted((spec["date"], p, len(users)) for p, users in expected.items())
    if sorted(rows) != oracle or any(type(r[2]) is not int for r in rows):
        raise ValueError("quality failed: output differs from independent distinct-user oracle")
    # A fresh connection writes only the validated, small business result.
    with duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as con:
        con.execute("CREATE TABLE result(business_date VARCHAR, province VARCHAR, active_users BIGINT)")
        con.executemany("INSERT INTO result VALUES (?,?,?)", oracle)
        con.execute("COPY result TO ? (FORMAT PARQUET)", [str(output)])
    durable(output)
    report = {"passed": True, "rows": len(rows), "output_hash": digest(output),
              "source_hash": spec["source_hash"], "date": spec["date"]}
    report_path = output.with_suffix(".quality.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False))
    durable(report_path)
    # Ensure directory entries precede the later metadata success commit.
    fd = os.open(output.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parent = json.loads(Path(sys.argv[1]).read_text())["parent_pid"]

    def guard():
        while True:
            if os.getppid() != parent:
                os._exit(73)
            time.sleep(0.1)

    threading.Thread(target=guard, daemon=True).start()
    calculate(json.loads(Path(sys.argv[1]).read_text()))
