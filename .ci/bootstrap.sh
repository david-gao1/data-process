#!/bin/sh
set -eu
python -c 'import sys; assert sys.platform=="linux" and sys.version_info[:3]==(3,11,17), "Linux Python 3.11.17 required"'
test "$(id -u)" -ne 0
command -v git >/dev/null
test "$(uv --version)" = 'uv 0.10.9'
if command -v sudo >/dev/null 2>&1; then
  echo 'sudo must not be available in the job environment' >&2
  exit 1
fi
uv sync --frozen --extra dev --group build --no-editable --python "$(command -v python)" --no-python-downloads
mkdir -p .ci-reports
