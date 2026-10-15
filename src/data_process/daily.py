"""One scheduled iteration; launchd owns timing, worker owns execution."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

from .core import Platform, TERMINAL, digest, iso
from .operations import validate_policy, record_status, emit_alert


def _daily(p, config, business_date=None, wait_seconds=120):
    day = iso(business_date or (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat())
    if config.get("auto_publish") is not True:
        raise ValueError("daily policy requires explicit auto_publish=true for a pinned release")
    if not config.get("enabled", True) or day > config.get("through_date", "9999-12-31"):
        return {"date": day, "state": "disabled_or_expired"}
    release = config["release_id"]
    p.verify_release(release)
    source_file = Path(config["inbox"]) / f"{day}.csv"
    marker = source_file.with_suffix(".ready")
    ready_hash = marker.read_text().strip()
    if ready_hash != digest(source_file.read_bytes()):
        raise ValueError("upstream ready marker checksum mismatch")
    source = p.ready(day, source_file)
    with p.db() as con:
        imported_hash = con.execute("SELECT hash FROM sources WHERE id=?", (source,)).fetchone()[0]
    if imported_hash != ready_hash:
        raise ValueError("source changed while importing ready snapshot")
    # Capture approval baseline before compute. A concurrent operator publication wins.
    with p.db() as con:
        row = con.execute("SELECT run FROM deliveries WHERE date=?", (day,)).fetchone()
        expected = row[0] if row else None
    run_id = p.submit(release, source, day, timeout=config.get("timeout", 60),
                      key=f"daily:{day}:{release}:{source}")
    deadline = time.monotonic() + wait_seconds
    while True:
        run = p.run(run_id)
        if run["state"] in TERMINAL:
            break
        if time.monotonic() >= deadline:
            raise ValueError("daily wait expired; inspect worker and queued run; no automatic retry")
        time.sleep(0.1)
    if run["state"] != "SUCCEEDED":
        raise ValueError(f"daily run {run_id} ended {run['state']}; publication blocked")
    # Idempotent trigger replay is allowed; an intervening different publication is not.
    with p.db() as con:
        current_row = con.execute("SELECT run FROM deliveries WHERE date=?", (day,)).fetchone()
        current = current_row[0] if current_row else None
        was_published = con.execute("SELECT 1 FROM audit WHERE run=?", (run_id,)).fetchone() is not None
    if was_published and current != run_id:
        raise ValueError("daily delivery was superseded; explicit operator action required")
    if current == run_id:
        return {"run_id": run_id, "state": "already_delivered", "date": day}
    result = p.publish(run_id, expected, config["actor"], f"approved daily policy; pinned release {release}")
    return {"run_id": run_id, "date": day, "publication": result}


def daily(p, config, business_date=None, wait_seconds=120):
    day = iso(business_date or (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat())
    try:
        validate_policy(p, config)
    except (ValueError, OSError, KeyError):
        record_status(p, f"daily:{day}", {"state": "failed", "code": "configuration_invalid"})
        emit_alert(p, "daily_failed", day, "configuration_invalid")
        raise
    try:
        result = _daily(p, config, day, wait_seconds)
        record_status(p, f"daily:{day}", {"state": result.get("state", "delivered"), "run_id": result.get("run_id")})
        return result
    except (ValueError, OSError, KeyError) as exc:
        code = "input_not_ready" if isinstance(exc, FileNotFoundError) else "daily_execution_failed"
        record_status(p, f"daily:{day}", {"state": "failed", "code": code})
        emit_alert(p, "daily_failed", day, code, config)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--date", help="explicit UTC business date for verified backfill")
    args = parser.parse_args()
    p = Platform(args.home)
    p.init()
    config = None
    try:
        config = json.loads(Path(args.config).read_text())
        print(json.dumps(daily(p, config, args.date), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError) as exc:
        day = args.date or (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        if config is None:
            emit_alert(p, "daily_failed", day, "configuration_load_failed")
        parser.exit(2, f"daily failed: {exc}\n")


if __name__ == "__main__":
    main()
