#!/bin/sh
# Manage only this project's three user-login services; no Library or machine-service writes.
set -eu
cd "$(dirname "$0")/.."
action=${1:-status}
data_dir=${2:-"$PWD/.data-process/live"}
policy_file=${3:-"$data_dir/daily-policy.json"}
domain="gui/$(id -u)"
start_services() {
  .venv/bin/python scripts/configure_launchd.py --home "$data_dir" --config "$policy_file"
  for role in worker daily monitor; do
    if ! launchctl print "$domain/local.data-process.$role" >/dev/null 2>&1; then
      launchctl bootstrap "$domain" ".data-process/launchd/local.data-process.$role.plist"
    fi
  done
  .venv/bin/python - "$data_dir" <<'PYCHECK'
import sys,time
from data_process.core import Platform
from data_process.operations import health
p=Platform(sys.argv[1])
deadline=time.monotonic()+10
while not health(p)['worker']['alive']:
    if time.monotonic()>=deadline:
        raise SystemExit('worker did not acquire a live heartbeat; inspect launchd logs')
    time.sleep(0.1)
PYCHECK
}
stop_services() {
  for role in monitor daily worker; do
    if launchctl print "$domain/local.data-process.$role" >/dev/null 2>&1; then
      launchctl bootout "$domain/local.data-process.$role"
      attempts=0
      while launchctl print "$domain/local.data-process.$role" >/dev/null 2>&1; do
        attempts=$((attempts + 1))
        if [ "$attempts" -ge 100 ]; then
          echo "service did not unload: $role" >&2
          exit 1
        fi
        sleep 0.1
      done
    fi
  done
}
case "$action" in
  start) start_services ;;
  stop) stop_services ;;
  restart)
    ./scripts/dp --home "$data_dir" config-check --config "$policy_file"
    stop_services
    start_services
    ;;
  status)
    for role in worker daily monitor; do
      job_state=$(launchctl print "$domain/local.data-process.$role")
      printf "%s\n" "$role"
      printf "%s\n" "$job_state" | awk '/^\t(state|pid|last exit code|run interval) =/ {print}'
    done
    ;;
  *) echo 'usage: services.sh start|stop|restart|status [data-dir] [policy-file]' >&2; exit 2 ;;
esac
