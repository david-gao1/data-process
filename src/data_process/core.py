"""Local state, release registry and governed delivery boundary."""
from contextlib import contextmanager
from datetime import date, timedelta
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import uuid

import duckdb

ROOT = Path(os.environ.get("DP_PROJECT_ROOT", Path.cwd())).resolve()
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "INTERRUPTED"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def iso(value):
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    return value


def durable_write(path, data):
    """Create once, sync bytes and directory. Caller uses content-addressed paths."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError("immutable content conflict")
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Platform:
    def __init__(self, home=None):
        self.home = Path(home or os.environ.get("DP_HOME", ROOT / ".data-process")).resolve()
        os.umask(0o077)

    @contextmanager
    def db(self, write=False):
        path = self.home / "control.sqlite"
        con = sqlite3.connect(f"file:{path}?mode={'rw' if write else 'ro'}", uri=True, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA synchronous=FULL")
        try:
            if write:
                con.execute("BEGIN IMMEDIATE")
            yield con
            if write:
                con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def init(self):
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.home.chmod(0o700)
        with sqlite3.connect(self.home / "control.sqlite") as con:
            con.executescript('''
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS releases(id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, date TEXT NOT NULL, hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(
              id TEXT PRIMARY KEY, release TEXT NOT NULL REFERENCES releases(id),
              source TEXT NOT NULL REFERENCES sources(id), date TEXT NOT NULL,
              state TEXT NOT NULL, timeout REAL NOT NULL, delay REAL NOT NULL,
              request_key TEXT UNIQUE, created TEXT DEFAULT CURRENT_TIMESTAMP,
              started TEXT, ended TEXT, message TEXT, output_hash TEXT, report_hash TEXT);
            CREATE TABLE IF NOT EXISTS deliveries(date TEXT PRIMARY KEY, run TEXT NOT NULL REFERENCES runs(id));
            CREATE TABLE IF NOT EXISTS audit(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
              previous_run TEXT, run TEXT NOT NULL REFERENCES runs(id), action TEXT NOT NULL,
              actor TEXT NOT NULL, reason TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
            ''')
        return {"home": str(self.home)}

    def release(self, definition):
        files = {"definition.sql": Path(definition).read_bytes(),
                 "compute.py": Path(__file__).with_name("compute.py").read_bytes(),
                 "uv.lock": (ROOT / "uv.lock").read_bytes()}
        manifest = {"files": {k: digest(v) for k, v in files.items()},
                    "duckdb": duckdb.__version__, "python": sys.version.split()[0], "contract": 1}
        encoded = json.dumps(manifest, sort_keys=True)
        release_id = digest(encoded.encode())
        for name, data in files.items():
            durable_write(self.home / "releases" / release_id / name, data)
        durable_write(self.home / "releases" / release_id / "manifest.json", encoded.encode())
        with self.db(True) as con:
            con.execute("INSERT OR IGNORE INTO releases VALUES (?,?)", (release_id, encoded))
        return release_id

    def verify_release(self, release_id):
        with self.db() as con:
            row = con.execute("SELECT manifest FROM releases WHERE id=?", (release_id,)).fetchone()
        if row is None:
            raise ValueError("release not found")
        encoded = row[0]
        if digest(encoded.encode()) != release_id:
            raise ValueError("release manifest checksum mismatch")
        manifest = json.loads(encoded)
        directory = self.home / "releases" / release_id
        for name, checksum in manifest["files"].items():
            if digest((directory / name).read_bytes()) != checksum:
                raise ValueError("release checksum mismatch")
        if manifest["duckdb"] != duckdb.__version__ or manifest["python"] != sys.version.split()[0]:
            raise ValueError("runtime mismatch; restore the recorded runtime")
        return directory

    def ready(self, business_date, source):
        iso(business_date)
        data = Path(source).read_bytes()
        source_hash = digest(data)
        source_id = digest((business_date + source_hash).encode())
        durable_write(self.home / "sources" / f"{source_id}.csv", data)
        with self.db(True) as con:
            con.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?)", (source_id, business_date, source_hash))
        return source_id

    def submit(self, release, source, business_date, timeout=60, delay=0, key=None):
        iso(business_date)
        if not math.isfinite(timeout) or not 0.1 <= timeout <= 3600:
            raise ValueError("timeout must be 0.1..3600 seconds")
        if not math.isfinite(delay) or not 0 <= delay <= 60:
            raise ValueError("test delay must be 0..60 seconds")
        self.verify_release(release)
        with self.db(True) as con:
            src = con.execute("SELECT * FROM sources WHERE id=?", (source,)).fetchone()
            if src is None or src["date"] != business_date:
                raise ValueError("source not ready for this business date")
            if key:
                old = con.execute("SELECT * FROM runs WHERE request_key=?", (key,)).fetchone()
                if old:
                    if tuple(old[k] for k in ("release", "source", "date", "timeout", "delay")) != (release, source, business_date, timeout, delay):
                        raise ValueError("idempotency key conflict")
                    return old["id"]
            run_id = uuid.uuid4().hex
            con.execute("INSERT INTO runs(id,release,source,date,state,timeout,delay,request_key) VALUES (?,?,?,?,'QUEUED',?,?,?)",
                        (run_id, release, source, business_date, timeout, delay, key))
        return run_id

    def run(self, run_id):
        with self.db() as con:
            row = con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("run not found")
        return dict(row)

    def runs(self):
        with self.db() as con:
            return [dict(r) for r in con.execute("SELECT * FROM runs ORDER BY created,id")]

    def cancel(self, run_id):
        with self.db(True) as con:
            row = con.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise ValueError("run not found")
            if row[0] == "QUEUED":
                con.execute("UPDATE runs SET state='CANCELLED',ended=CURRENT_TIMESTAMP,message='cancelled before start' WHERE id=?", (run_id,))
            elif row[0] == "RUNNING":
                con.execute("UPDATE runs SET state='CANCELLING' WHERE id=?", (run_id,))
        return self.run(run_id)

    def artifact(self, run_id):
        # Only validated ids from the registry are used to construct paths.
        self.run(run_id)
        return self.home / "candidates" / run_id / "result.parquet"

    def verify_artifact(self, row):
        if row["state"] != "SUCCEEDED":
            raise ValueError("only a successful quality-checked run can be delivered")
        path = self.artifact(row["id"])
        report = path.with_suffix(".quality.json")
        if digest(path.read_bytes()) != row["output_hash"] or digest(report.read_bytes()) != row["report_hash"]:
            raise ValueError("artifact or quality report checksum mismatch")
        quality = json.loads(report.read_text())
        if not quality["passed"] or quality["date"] != row["date"] or quality["output_hash"] != row["output_hash"]:
            raise ValueError("quality report invalid")
        return path

    def publish(self, run_id, expected, actor, reason, rollback=False):
        if not actor.strip() or not reason.strip():
            raise ValueError("actor and reason required")
        row = self.run(run_id)
        self.verify_release(row["release"])
        self.verify_artifact(row)
        with self.db(True) as con:
            current_row = con.execute("SELECT run FROM deliveries WHERE date=?", (row["date"],)).fetchone()
            current = current_row[0] if current_row else None
            if current != expected:
                raise ValueError("publication conflict: expected current run does not match")
            if con.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0] != "SUCCEEDED":
                raise ValueError("run is no longer successful")
            if rollback and not con.execute("SELECT 1 FROM audit WHERE run=?", (run_id,)).fetchone():
                raise ValueError("rollback target has never been published")
            if current == run_id:
                return {"run": run_id, "changed": False}
            con.execute("INSERT INTO deliveries VALUES (?,?) ON CONFLICT(date) DO UPDATE SET run=excluded.run", (row["date"], run_id))
            con.execute("INSERT INTO audit(date,previous_run,run,action,actor,reason) VALUES (?,?,?,?,?,?)",
                        (row["date"], current, run_id, "rollback" if rollback else "publish", actor, reason))
        return {"run": run_id, "previous": current, "changed": True}

    def trend(self, end, days=30):
        iso(end)
        if not 1 <= days <= 30:
            raise ValueError("days must be 1..30")
        start = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
        with self.db() as con:
            rows = [dict(r) for r in con.execute("SELECT r.* FROM deliveries d JOIN runs r ON r.id=d.run WHERE d.date BETWEEN ? AND ? ORDER BY d.date", (start, end))]
        result = []
        with duckdb.connect(config={"threads": 1}) as con:
            for row in rows:
                path = self.verify_artifact(row)
                for business_date, province, active_users in con.execute("SELECT * FROM read_parquet(?) ORDER BY province", [str(path)]).fetchall():
                    result.append(dict(business_date=business_date, province=province, active_users=active_users,
                                       run_id=row["id"], release_id=row["release"], source_id=row["source"]))
        present = {r["date"] for r in rows}
        missing = [(date.fromisoformat(start) + timedelta(days=i)).isoformat() for i in range(days)
                   if (date.fromisoformat(start) + timedelta(days=i)).isoformat() not in present]
        return {"start": start, "end": end, "rows": result, "missing_dates": missing}

    def audit(self):
        with self.db() as con:
            return [dict(r) for r in con.execute("SELECT * FROM audit ORDER BY seq")]

    def backup(self, destination):
        # Worker lock excludes active calculation/recovery; BEGIN IMMEDIATE fences CLI writers.
        import fcntl
        import shutil
        destination = Path(destination).resolve()
        if destination == self.home or self.home in destination.parents:
            raise ValueError("backup must be outside the data home")
        with (self.home / "worker.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.db(True) as con:
                if con.execute("SELECT 1 FROM runs WHERE state IN ('RUNNING','CANCELLING')").fetchone():
                    raise ValueError("reconcile interrupted runs before backup")
                shutil.copytree(self.home, destination)
        return {"backup": str(destination)}

    def check(self):
        with self.db() as con:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or con.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("control database integrity failure")
            releases = [r[0] for r in con.execute("SELECT id FROM releases")]
            sources = [dict(r) for r in con.execute("SELECT * FROM sources")]
            successful = [dict(r) for r in con.execute("SELECT * FROM runs WHERE state='SUCCEEDED'")]
        for release in releases:
            self.verify_release(release)
        for source in sources:
            if digest((self.home / "sources" / f'{source["id"]}.csv').read_bytes()) != source["hash"]:
                raise ValueError("source checksum mismatch")
        for run in successful:
            self.verify_artifact(run)
        return {"integrity": "ok", "releases": len(releases), "sources": len(sources), "successful_runs": len(successful)}


def demo_csv(path, business_date):
    iso(business_date)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["business_date", "user_id", "province"])
        for province, count in [("北京", 3), ("上海", 4), ("广东", 5)]:
            for user in range(count):
                writer.writerow([business_date, f"synthetic-{user}", province])
                writer.writerow([business_date, f"synthetic-{user}", province])
    return {"file": str(path), "synthetic": True, "expected": {"北京": 3, "上海": 4, "广东": 5}}
