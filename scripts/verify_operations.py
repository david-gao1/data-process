"""Local failure/overdue notification proof with an explicit synthetic clock; no messages sent."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from data_process.core import Platform, ROOT
from data_process.daily import daily
from data_process.operations import health, monitor, validate_policy

home = Path(sys.argv[1] if len(sys.argv) > 1 else '.data-process/ops-proof').resolve()
if home.exists():
    raise SystemExit('use a fresh proof directory; existing state is never overwritten')
p = Platform(home)
p.init()
inbox = home / 'inbox'
inbox.mkdir()
config = {'auto_publish': True, 'release_id': p.release(ROOT / 'definitions/daily_active.sql'),
          'inbox': str(inbox), 'actor': 'local-notification-proof', 'deadline_utc_hour': 8,
          'alerts': {'sink': 'local', 'enabled': True}}
validate_policy(p, config)
for _ in range(2):
    try:
        daily(p, config, '2026-10-14')
    except FileNotFoundError:
        pass
    else:
        raise AssertionError('missing readiness unexpectedly succeeded')
clock = datetime(2026, 10, 15, 9, tzinfo=timezone.utc)
monitor(p, config, clock)
monitor(p, config, clock)
files = sorted((home / 'notifications').glob('*.json'))
assert len(files) == 3
payloads = [json.loads(path.read_text()) for path in files]
assert {item['event'] for item in payloads} == {'daily_failed', 'delivery_overdue', 'worker_unhealthy'}
assert not p.runs() and not p.audit()
result = {'synthetic_clock_utc': clock.isoformat(), 'home': str(home), 'external_messages_sent': 0,
          'repeated_daily_attempts': 2, 'repeated_monitor_attempts': 2, 'notification_files': len(files),
          'notifications': payloads, 'health': health(p, config, clock), 'integrity': p.check()}
print(json.dumps(result, ensure_ascii=False, indent=2))
