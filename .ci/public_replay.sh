#!/bin/sh
set -eu
mkdir -p .ci-state .ci-reports
private_home="$PWD/.ci-state/public-retail"
if [ -e "$private_home" ] || [ -e "$private_home-backup" ]; then
  echo 'public replay requires a fresh private workspace' >&2
  exit 2
fi
status=0
phase=download
.venv/bin/python -m data_process.public_retail --home "$private_home" fetch > .ci-state/public-download.json 2> .ci-state/public-error.log || status=$?
if [ "$status" -eq 0 ]; then
  phase=business_e2e
  .venv/bin/python scripts/retail_e2e.py "$private_home" > .ci-state/public-result.json 2> .ci-state/public-error.log || status=$?
fi
.venv/bin/python .ci/public_status.py "$status" "$phase"
exit "$status"
