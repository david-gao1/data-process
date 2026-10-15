#!/bin/sh
set -eu
python -c 'import sys; assert sys.platform=="linux" and sys.version_info[:3]==(3,11,17), "Linux Python 3.11.17 required"'
python -m pip install --disable-pip-version-check 'uv==0.10.9'
uv sync --frozen --extra dev --group build --no-editable --python "$(command -v python)" --no-python-downloads
mkdir -p .ci-reports
