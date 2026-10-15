"""Reproducible complete CLI E2E, leaving a private local demo product."""
from datetime import date, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    home = Path(sys.argv[1] if len(sys.argv) > 1 else ".data-process/demo").resolve()
    if home.exists():
        raise SystemExit("use a fresh directory; existing demo data is never overwritten")
    env = dict(os.environ, DP_HOME=str(home))

    def dp(*args):
        completed = subprocess.run([sys.executable, "-m", "data_process.cli", *args], env=env,
                                   text=True, capture_output=True, check=True)
        return json.loads(completed.stdout)

    dp("init")
    release = dp("release")["release_id"]
    end = date(2026, 10, 14)
    runs = []
    for i in range(30):
        business_date = (end - timedelta(days=29 - i)).isoformat()
        source_file = home / f"demo-{business_date}.csv"
        dp("demo-source", "--date", business_date, "--output", str(source_file))
        source = dp("ready", "--date", business_date, "--file", str(source_file))["source_id"]
        run = dp("submit", "--release", release, "--source", source, "--date", business_date)["run_id"]
        runs.append(run)
    log = (home / "worker.log").open("w")
    process = subprocess.Popen([sys.executable, "-m", "data_process.cli", "worker"], env=env,
                               stdout=log, stderr=subprocess.STDOUT)
    try:
        for run in runs:
            dp("wait", run)
            dp("publish", run, "--expected", "NONE", "--actor", "demo-operator", "--reason", "synthetic data verified")
        trend = dp("trend", "--end", end.isoformat())
        assert len(trend["rows"]) == 90 and not trend["missing_dates"]
        assert {r["province"]: r["active_users"] for r in trend["rows"]} == {"北京": 3, "上海": 4, "广东": 5}
        report = {"synthetic": True, "home": str(home), "release_id": release,
                  "days": 30, "rows": 90, "integrity": dp("check"), "last_run": runs[-1],
                  "last_day": trend["rows"][-3:]}
        (home / "demo-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()


if __name__ == "__main__":
    main()
