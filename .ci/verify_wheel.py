"""Verify artifact identity before installing; prints no runtime data."""
import hashlib,json,os
from pathlib import Path

out=Path('dist')
m=json.loads((out/'manifest.json').read_text())
for name,key in [(m['wheel'],'wheel_sha256'),('runtime-requirements.txt','runtime_requirements_sha256')]:
    path=out/name
    if path.parent != out or hashlib.sha256(path.read_bytes()).hexdigest()!=m[key]:
        raise SystemExit('artifact checksum mismatch')
if os.environ.get('CI_COMMIT_SHA') and m['commit_sha'] != os.environ['CI_COMMIT_SHA']:
    raise SystemExit('artifact was built from a different commit')
print(m['commit_sha'])
