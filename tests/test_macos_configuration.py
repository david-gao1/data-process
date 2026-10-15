"""macOS configuration validation only; never loads or restarts resident services."""
import plistlib
from pathlib import Path
import subprocess
import sys

import pytest

from data_process.core import Platform, ROOT

pytestmark=[pytest.mark.macos,pytest.mark.skipif(sys.platform!='darwin',reason='macOS configuration suite')]


def test_launchd_plists_are_valid_and_have_bounded_roles(tmp_path):
    import json
    p=Platform(tmp_path/'home');p.init()
    inbox=tmp_path/'inbox';inbox.mkdir()
    release=p.release(ROOT/'definitions/daily_active.sql')
    policy=tmp_path/'policy.json'
    policy.write_text(json.dumps({'auto_publish':True,'release_id':release,'inbox':str(inbox),'actor':'test'}))
    output=tmp_path/'plists'
    subprocess.run([sys.executable,str(ROOT/'scripts/configure_launchd.py'),'--home',str(p.home),'--config',str(policy),'--output',str(output)],check=True,capture_output=True)
    specs={path.stem:plistlib.loads(path.read_bytes()) for path in output.glob('*.plist')}
    assert len(specs)==3
    assert specs['local.data-process.worker']['KeepAlive'] is True
    assert 'KeepAlive' not in specs['local.data-process.daily']
    assert specs['local.data-process.monitor']['StartInterval']==3600
    subprocess.run(['plutil','-lint',*[str(path) for path in output.glob('*.plist')]],check=True,capture_output=True)
