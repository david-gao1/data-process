"""Generate project-local macOS LaunchAgents; loading is an explicit separate command."""
import argparse
from pathlib import Path
import plistlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--home", required=True)
parser.add_argument("--config", required=True)
parser.add_argument("--output", default=".data-process/launchd")
args = parser.parse_args()
home = Path(args.home).resolve()
config = Path(args.config).resolve()
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
python = str(Path(sys.executable).absolute())
root = str(Path(__file__).resolve().parents[1])
for role in ("worker", "daily"):
    label = f"local.data-process.{role}"
    command = ([python, "-m", "data_process.cli", "--home", str(home), "worker"] if role == "worker"
               else [python, "-m", "data_process.daily", "--home", str(home), "--config", str(config)])
    spec = {"Label": label, "ProgramArguments": command, "WorkingDirectory": root,
            "StandardOutPath": str(home / f"launchd-{role}.log"),
            "StandardErrorPath": str(home / f"launchd-{role}.error.log"), "Umask": 0o077,
            "ProcessType": "Background", "ThrottleInterval": 10}
    if role == "worker":
        spec.update(RunAtLoad=True, KeepAlive=True)
    else:
        # Mac local timezone. The task's local timezone is Etc/UTC; calculation uses UTC.
        spec["StartCalendarInterval"] = {"Hour": 8, "Minute": 0}
    path = output / f"{label}.plist"
    path.write_bytes(plistlib.dumps(spec))
    print(path)
