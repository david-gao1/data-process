"""Single local executor, with no calendar scheduling or automatic retry."""
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
import uuid

from .core import Platform, digest, durable_write
from .operations import heartbeat, emit_alert, flush_alerts, validate_policy


def stop_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def worker(platform: Platform, once=False, policy=None):
    platform.init()
    if policy is not None:
        validate_policy(platform, policy)
    stopping = False
    owner = uuid.uuid4().hex
    owns_lock = False
    last_heartbeat = 0

    def tick():
        nonlocal last_heartbeat
        if time.monotonic() - last_heartbeat >= 1:
            heartbeat(platform, owner)
            last_heartbeat = time.monotonic()

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    previous = {s: signal.signal(s, stop) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        with (platform.home / "worker.lock").open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("another worker or its surviving child holds the lock")
            owns_lock = True
            tick()
            flush_alerts(platform)
            with platform.db(True) as con:
                con.execute("UPDATE runs SET state=CASE WHEN state='CANCELLING' THEN 'CANCELLED' ELSE 'INTERRUPTED' END, ended=CURRENT_TIMESTAMP, message='worker restart reconciliation; no automatic retry' WHERE state IN ('RUNNING','CANCELLING')")
            print("worker ready; restart reconciliation complete", flush=True)
            while not stopping:
                tick()
                with platform.db(True) as con:
                    row = con.execute("SELECT * FROM runs WHERE state='QUEUED' ORDER BY created,rowid LIMIT 1").fetchone()
                    if row:
                        row = dict(row)
                        con.execute("UPDATE runs SET state='RUNNING',started=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
                if not row:
                    if once:
                        return
                    time.sleep(0.1)
                    continue
                state, message, output_hash, report_hash = "FAILED", "", None, None
                process = None
                try:
                    release_dir = platform.verify_release(row["release"])
                    with platform.db() as con:
                        src = dict(con.execute("SELECT * FROM sources WHERE id=?", (row["source"],)).fetchone())
                    output = platform.artifact(row["id"])
                    spec = {"source": str(platform.home / "sources" / f'{row["source"]}.csv'),
                            "source_hash": src["hash"], "output": str(output), "date": row["date"],
                            "sql": str(release_dir / "definition.sql"), "delay": row["delay"], "parent_pid": os.getpid()}
                    spec_path = output.parent / "spec.json"
                    durable_write(spec_path, json.dumps(spec).encode())
                    with (output.parent / "run.log").open("xb") as log:
                        # Minimal environment avoids leaking database/cloud credentials to SQL work.
                        env = {"PATH": os.defpath, "PYTHONUNBUFFERED": "1"}
                        started = time.monotonic()
                        process = subprocess.Popen([sys.executable, str(release_dir / "compute.py"), str(spec_path)],
                                                   stdout=log, stderr=subprocess.STDOUT, env=env,
                                                   pass_fds=(lock.fileno(),), cwd=output.parent)
                        while True:
                            tick()
                            if stopping:
                                state, message = "INTERRUPTED", "worker stopped; explicit rerun required"
                                stop_process(process)
                                break
                            if platform.run(row["id"])["state"] == "CANCELLING":
                                state, message = "CANCELLED", "local calculation terminated and reaped"
                                stop_process(process)
                                break
                            if time.monotonic() - started >= row["timeout"]:
                                state, message = "TIMED_OUT", "local calculation exceeded timeout and was reaped"
                                stop_process(process)
                                break
                            code = process.poll()
                            if code is not None:
                                if code != 0:
                                    raise ValueError(f"calculation exited {code}; see run.log")
                                report = output.with_suffix(".quality.json")
                                quality = json.loads(report.read_text())
                                output_hash, report_hash = digest(output.read_bytes()), digest(report.read_bytes())
                                if not quality["passed"] or quality["output_hash"] != output_hash or quality["source_hash"] != src["hash"] or quality["date"] != row["date"]:
                                    raise ValueError("invalid quality report")
                                state, message = "SUCCEEDED", "candidate quality checks passed; approval required"
                                break
                            time.sleep(0.05)
                except Exception as exc:
                    message = str(exc)
                finally:
                    if process is not None:
                        stop_process(process)
                    state = platform.finish_run(row["id"], state, message, output_hash, report_hash)
                    if state != "SUCCEEDED":
                        emit_alert(platform, "run_failed", row["id"], state, policy)
                    print(json.dumps({"run": row["id"], "state": state, "message": message}), flush=True)
                if once:
                    return
    finally:
        if owns_lock:
            heartbeat(platform, owner, "stopped")
        for sig, handler in previous.items():
            signal.signal(sig, handler)
