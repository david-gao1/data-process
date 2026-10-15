"""One scheduled iteration; launchd owns timing, worker owns execution."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

from .core import Platform, TERMINAL, digest, iso


def daily(p, config, business_date=None, wait_seconds=120):
    day = iso(business_date or (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat())
    if config.get("auto_publish") is not True:
        raise ValueError("daily policy requires explicit auto_publish=true for a pinned release")
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
    was_published = any(entry["run"] == run_id for entry in p.audit())
    if was_published and expected != run_id:
        raise ValueError("daily delivery was superseded; explicit operator action required")
    if expected == run_id:
        return {"run_id": run_id, "state": "already_delivered", "date": day}
    result = p.publish(run_id, expected, config["actor"], f"approved daily policy; pinned release {release}")
    return {"run_id": run_id, "date": day, "publication": result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--date", help="explicit UTC business date for verified backfill")
    args = parser.parse_args()
    try:
        print(json.dumps(daily(Platform(args.home), json.loads(Path(args.config).read_text()), args.date), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"daily failed: {exc}\n")


if __name__ == "__main__":
    main()
