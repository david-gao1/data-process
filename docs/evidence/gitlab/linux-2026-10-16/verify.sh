#!/bin/sh
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends git
mkdir /work
git clone -q /input/source.bundle /work/repo
cd /work/repo
export CI_COMMIT_SHA=$(git rev-parse HEAD)
export UV_CACHE_DIR=/work/uv-cache
sh .ci/bootstrap.sh
.venv/bin/python .ci/check_config.py > /results/offline-config.json
.venv/bin/python -m pytest -m 'not macos' --junitxml=/results/junit.xml -q
.venv/bin/python -I -m data_process.smoke --output /results/source-smoke.json
.venv/bin/python .ci/build_wheel.py
sh .ci/installed_smoke.sh
cp dist/manifest.json /results/wheel-manifest.json
cp .ci-reports/installed-smoke.json /results/installed-smoke.json
python -c 'import json,platform,sys; print(json.dumps({"python":platform.python_version(),"system":platform.system(),"machine":platform.machine(),"passed":True}))' > /results/environment.json
