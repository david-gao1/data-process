"""Generate project-local macOS LaunchAgents; loading is an explicit separate command."""
import argparse
from pathlib import Path
import plistlib
import sys
import json
from data_process.core import Platform
from data_process.operations import validate_policy

parser = argparse.ArgumentParser()
parser.add_argument("--home", required=True)
parser.add_argument("--config", required=True)
parser.add_argument("--output", default=".data-process/launchd")
args = parser.parse_args()
home = Path(args.home).resolve()
config = Path(args.config).resolve()
output = Path(args.output).resolve()
validate_policy(Platform(home), json.loads(config.read_text()))
output.mkdir(parents=True, exist_ok=True)
python = str(Path(sys.executable).absolute())
root = str(Path(__file__).resolve().parents[1])
for role in ("worker", "daily", "monitor"):
    label = f"local.data-process.{role}"
    if role == "worker":
        command = [python, "-m", "data_process.cli", "--home", str(home), "worker", "--policy", str(config)]
    elif role == "daily":
        command = [python, "-m", "data_process.daily", "--home", str(home), "--config", str(config)]
    else:
        command = [python, "-m", "data_process.cli", "--home", str(home), "monitor", "--config", str(config)]
    spec = {"Label": label, "ProgramArguments": command, "WorkingDirectory": root,
            "StandardOutPath": str(home / f"launchd-{role}.log"),
            "StandardErrorPath": str(home / f"launchd-{role}.error.log"), "Umask": 0o077,
            "ProcessType": "Background", "ThrottleInterval": 10}
    if role == "worker":
        spec.update(RunAtLoad=True, KeepAlive=True)
    elif role == "daily":
        # launchd calendar uses system local timezone; business date calculation uses UTC.
        spec["StartCalendarInterval"] = {"Hour": 8, "Minute": 0}
    else:
        spec["StartInterval"] = 3600
    path = output / f"{label}.plist"
    path.write_bytes(plistlib.dumps(spec))
    print(path)
