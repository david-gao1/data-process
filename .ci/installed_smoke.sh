#!/bin/sh
set -eu
python_runner=${DP_PYTHON:-python}
commit=$("$python_runner" .ci/verify_wheel.py)
if [ -e .wheel-venv ]; then
  echo "use a fresh wheel validation workspace" >&2
  exit 2
fi
uv venv --python "$python_runner" .wheel-venv
uv pip install --python .wheel-venv/bin/python --require-hashes -r dist/runtime-requirements.txt
uv pip install --python .wheel-venv/bin/python --no-deps dist/*.whl
mkdir -p .ci-reports
# -I ignores checkout/PYTHONPATH; smoke children work outside the repository.
.wheel-venv/bin/python -I -m data_process.smoke --expect-commit "$commit" --output .ci-reports/installed-smoke.json
