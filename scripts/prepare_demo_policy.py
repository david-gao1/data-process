from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from data_process.core import Platform, ROOT, demo_csv, digest
home = ROOT / '.data-process/live'
p = Platform(home)
p.init()
release = p.release(ROOT / 'definitions/daily_active.sql')
inbox = home / 'inbox'
inbox.mkdir(exist_ok=True)
day = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
source = inbox / f'{day}.csv'
if not source.exists():
    demo_csv(source, day)
source.with_suffix('.ready').write_text(digest(source.read_bytes()))
policy = {'auto_publish': True, 'release_id': release, 'inbox': str(inbox), 'actor': 'synthetic-demo-daily-policy', 'timeout': 60, 'through_date': day, 'deadline_utc_hour': 8, 'alerts': {'sink': 'local', 'enabled': True}}
(home / 'daily-policy.json').write_text(json.dumps(policy, ensure_ascii=False, indent=2))
print(json.dumps({'home': str(home), 'release': release, 'synthetic_date': day}, indent=2))
