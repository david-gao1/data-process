"""Operator CLI. JSON outputs are suitable for scripts and Excel export."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time
import duckdb

from .core import Platform, ROOT, ASSET_ROOT, TERMINAL, demo_csv
from .worker import worker
from .operations import health, monitor, validate_policy


def main():
    parser = argparse.ArgumentParser(description="本地受控数据交付；所有数据默认为合成演示")
    parser.add_argument("--home", help="state directory; default DP_HOME or project .data-process")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("init")
    sub = subs.add_parser("demo-source")
    sub.add_argument("--date", required=True)
    sub.add_argument("--output", required=True)
    sub = subs.add_parser("ready")
    sub.add_argument("--date", required=True)
    sub.add_argument("--file", required=True)
    sub = subs.add_parser("release")
    sub.add_argument("--product", choices=["daily_active", "retail_daily"], default="daily_active")
    sub.add_argument("--sql")
    sub = subs.add_parser("submit")
    sub.add_argument("--release", required=True)
    sub.add_argument("--source", required=True)
    sub.add_argument("--date", required=True)
    sub.add_argument("--timeout", type=float, default=60)
    sub.add_argument("--key")
    sub.add_argument("--test-delay", type=float, default=0, help="fault injection seconds, recorded in run")
    sub = subs.add_parser("worker")
    sub.add_argument("--policy", help="validated daily policy, including local alert settings")
    sub.add_argument("--once", action="store_true", help="reconcile then process at most one queued run")
    subs.add_parser("runs")
    for command in ("status", "logs", "cancel", "inspect", "wait"):
        sub = subs.add_parser(command)
        sub.add_argument("run")
        if command == "wait":
            sub.add_argument("--seconds", type=float, default=90)
    for command in ("publish", "rollback"):
        sub = subs.add_parser(command)
        sub.add_argument("run")
        sub.add_argument("--expected", required=True, help="current run id, or NONE for first publication")
        sub.add_argument("--actor", required=True)
        sub.add_argument("--reason", required=True)
    sub = subs.add_parser("trend")
    sub.add_argument("--end", required=True)
    sub.add_argument("--days", type=int, default=30)
    subs.add_parser("audit")
    subs.add_parser("check")
    subs.add_parser("notifications")
    for command in ("health", "monitor", "config-check"):
        sub = subs.add_parser(command)
        sub.add_argument("--config", required=command != "health")
    sub = subs.add_parser("backup")
    sub.add_argument("destination")
    args = parser.parse_args()
    p = Platform(args.home)
    try:
        if args.command == "init":
            result = p.init()
        elif args.command == "demo-source":
            result = demo_csv(args.output, args.date)
        elif args.command == "release":
            result = {"release_id": p.release(args.sql or ASSET_ROOT / "definitions" / ("retail_daily.sql" if args.product == "retail_daily" else "daily_active.sql"), args.product)}
        elif args.command == "ready":
            result = {"source_id": p.ready(args.date, args.file)}
        elif args.command == "submit":
            result = {"run_id": p.submit(args.release, args.source, args.date, args.timeout, args.test_delay, args.key)}
        elif args.command == "worker":
            policy = json.loads(Path(args.policy).read_text()) if args.policy else None
            worker(p, args.once, policy)
            return
        elif args.command == "runs":
            result = p.runs()
        elif args.command == "status":
            result = p.run(args.run)
        elif args.command == "wait":
            deadline = time.monotonic() + args.seconds
            while True:
                result = p.run(args.run)
                if result["state"] in TERMINAL:
                    break
                if time.monotonic() >= deadline:
                    raise ValueError("wait deadline exceeded; run continues asynchronously")
                time.sleep(0.1)
        elif args.command == "inspect":
            row = p.run(args.run)
            release = p.verify_release(row["release"])
            result = {"run": row, "manifest": json.loads((release / "manifest.json").read_text()),
                      "definition": (release / "definition.sql").read_text()}
        elif args.command == "logs":
            print((p.artifact(args.run).parent / "run.log").read_text())
            return
        elif args.command == "cancel":
            result = p.cancel(args.run)
        elif args.command in ("publish", "rollback"):
            result = p.publish(args.run, None if args.expected == "NONE" else args.expected,
                               args.actor, args.reason, args.command == "rollback")
        elif args.command == "trend":
            result = p.trend(args.end, args.days)
        elif args.command == "audit":
            result = p.audit()
        elif args.command == "check":
            result = p.check()
        elif args.command == "notifications":
            with p.db() as con:
                result = [dict(r) for r in con.execute("SELECT * FROM notifications ORDER BY rowid")]
        elif args.command in ("health", "monitor", "config-check"):
            config = json.loads(Path(args.config).read_text()) if args.config else None
            if args.command == "config-check":
                validate_policy(p, config)
                result = {"configuration": "valid", "release_id": config["release_id"]}
            else:
                result = monitor(p, config) if args.command == "monitor" else health(p, config)
        elif args.command == "backup":
            result = p.backup(args.destination)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command in ("health", "monitor") and not result["healthy"]:
            sys.exit(1)
        if args.command == "wait" and result["state"] != "SUCCEEDED":
            sys.exit(1)
    except (ValueError, OSError, sqlite3.Error, KeyError, duckdb.Error) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
