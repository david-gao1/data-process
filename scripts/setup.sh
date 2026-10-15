#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv sync --frozen --extra dev --no-editable --reinstall-package data-process
.venv/bin/python -c 'import data_process,duckdb; print("ready: DuckDB",duckdb.__version__)'
