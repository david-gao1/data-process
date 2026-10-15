"""Local health and transactional notification outbox; never sends externally."""
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import time

from .core import digest, durable_write, iso

EVENTS = {"run_failed", "daily_failed", "delivery_overdue", "worker_unhealthy"}


def validate_policy(p, config):
    if not isinstance(config, dict):
        raise ValueError("policy must be an object")
    allowed = {"auto_publish", "release_id", "inbox", "actor", "timeout", "enabled", "through_date", "deadline_utc_hour", "alerts"}
    if set(config) - allowed:
        raise ValueError("unknown policy fields")
    if config.get("auto_publish") is not True:
        raise ValueError("daily policy requires explicit auto_publish=true for a pinned release")
    if type(config.get("enabled", True)) is not bool:
        raise ValueError("enabled must be boolean")
    release = config.get("release_id")
    if not isinstance(release, str) or len(release) != 64:
        raise ValueError("release_id must be a registered SHA256")
    p.verify_release(release)
    inbox = config.get("inbox")
    if not isinstance(inbox, str) or not Path(inbox).is_absolute() or not Path(inbox).is_dir():
        raise ValueError("inbox must be an existing absolute directory")
    if not isinstance(config.get("actor"), str) or not config["actor"].strip():
        raise ValueError("actor is required")
    timeout = config.get("timeout", 60)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0.1 <= timeout <= 3600:
        raise ValueError("timeout must be 0.1..3600 seconds")
    hour = config.get("deadline_utc_hour", 8)
    if type(hour) is not int or not 0 <= hour <= 23:
        raise ValueError("deadline_utc_hour must be 0..23")
    if "through_date" in config:
        if not isinstance(config["through_date"], str):
            raise ValueError("through_date must be an ISO date string")
        iso(config["through_date"])
    alerts = config.get("alerts", {})
    if not isinstance(alerts, dict) or set(alerts) - {"enabled", "events", "sink"}:
        raise ValueError("invalid alerts fields")
    if type(alerts.get("enabled", True)) is not bool or alerts.get("sink", "local") != "local":
        raise ValueError("only boolean enabled and local notification sink are supported")
    events = alerts.get("events", sorted(EVENTS))
    if not isinstance(events, list) or any(not isinstance(e, str) or e not in EVENTS for e in events):
        raise ValueError("invalid notification events")
    return config


def flush_alerts(p):
    # Serialize file delivery with the same database lock as outbox state.
    # If a write fails, pending rows remain and immutable files can be replayed.
    with p.db(True) as con:
        rows = con.execute("SELECT id,payload FROM notifications WHERE delivered=0 ORDER BY rowid").fetchall()
        for row in rows:
            durable_write(p.home / "notifications" / f'{row["id"]}.json', row["payload"].encode())
            con.execute("UPDATE notifications SET delivered=1 WHERE id=?", (row["id"],))
    return len(rows)


def emit_alert(p, event, scope, code, config=None):
    settings = (config or {}).get("alerts", {})
    if not settings.get("enabled", True) or event not in settings.get("events", sorted(EVENTS)):
        return None
    alert_id = digest(f"{event}:{scope}".encode())
    # No exception text, SQL, input contents, credentials or arbitrary config in notifications.
    payload = json.dumps({"id": alert_id, "event": event, "scope": scope, "code": code,
                          "created_utc": datetime.now(timezone.utc).isoformat()}, sort_keys=True)
    with p.db(True) as con:
        con.execute("INSERT OR IGNORE INTO notifications(id,payload,delivered) VALUES (?,?,0)", (alert_id, payload))
    flush_alerts(p)
    return alert_id


def record_status(p, key, value):
    with p.db(True) as con:
        con.execute("INSERT INTO operational_status VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value, sort_keys=True)))


def heartbeat(p, owner, status="running"):
    value = json.dumps({"owner": owner, "status": status, "updated": time.time()})
    with p.db(True) as con:
        previous = con.execute("SELECT value FROM operational_status WHERE key='worker'").fetchone()
        if status == "stopped" and previous and json.loads(previous[0])["owner"] != owner:
            return
        con.execute("INSERT INTO operational_status VALUES ('worker',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (value,))


def health(p, config=None, now=None):
    now = now or datetime.now(timezone.utc)
    with p.db() as con:
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("control database integrity failure")
        rows = {r["key"]: json.loads(r["value"]) for r in con.execute("SELECT * FROM operational_status")}
        counts = {r[0]: r[1] for r in con.execute("SELECT state,COUNT(*) FROM runs GROUP BY state")}
        queued = con.execute("SELECT MIN(created) FROM runs WHERE state='QUEUED'").fetchone()[0]
        running = [dict(r) for r in con.execute("SELECT id,started,timeout FROM runs WHERE state IN ('RUNNING','CANCELLING')")]
        pending = con.execute("SELECT COUNT(*) FROM notifications WHERE delivered=0").fetchone()[0]
        deliveries = {r[0] for r in con.execute("SELECT date FROM deliveries")}
    worker = rows.get("worker", {})
    age = max(0, now.timestamp() - worker.get("updated", 0)) if worker else None
    worker_ok = bool(worker) and worker.get("status") == "running" and age <= 10
    overdue_runs = [r["id"] for r in running if now.timestamp() - datetime.fromisoformat(r["started"]).replace(tzinfo=timezone.utc).timestamp() > r["timeout"] + 5]
    queue_age = max(0, now.timestamp() - datetime.fromisoformat(queued).replace(tzinfo=timezone.utc).timestamp()) if queued else None
    delivery = {"expected_date": None, "state": "not_configured"}
    if config is not None:
        validate_policy(p, config)
        day = (now.date() - timedelta(days=1)).isoformat()
        if not config.get("enabled", True) or day > config.get("through_date", "9999-12-31"):
            delivery = {"expected_date": day, "state": "disabled_or_expired"}
        else:
            source = Path(config["inbox"]) / f"{day}.csv"
            ready = source.exists() and source.with_suffix(".ready").exists()
            state = "delivered" if day in deliveries else ("overdue" if now.hour >= config.get("deadline_utc_hour", 8) else "waiting")
            delivery = {"expected_date": day, "state": state, "ready_files_present": ready,
                        "last_attempt": rows.get(f"daily:{day}")}
    return {"healthy": worker_ok and not overdue_runs and pending == 0 and delivery["state"] != "overdue",
            "worker": {"alive": worker_ok, "heartbeat_age_seconds": age, "status": worker.get("status", "unknown")},
            "run_counts": counts, "oldest_queue_age_seconds": queue_age, "overdue_runs": overdue_runs,
            "pending_notifications": pending, "delivery": delivery}


def monitor(p, config, now=None):
    validate_policy(p, config)
    flush_alerts(p)
    result = health(p, config, now)
    day = result["delivery"]["expected_date"]
    if not result["worker"]["alive"]:
        emit_alert(p, "worker_unhealthy", day, "worker_heartbeat_missing_or_stale", config)
    if result["delivery"]["state"] == "overdue":
        emit_alert(p, "delivery_overdue", day, "expected_business_date_not_published", config)
    return result
