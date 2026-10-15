"""Artifact boundary and installed-resource checks, independent of a GitLab connection."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from data_process.core import ASSET_ROOT, ROOT


def config_checker():
    spec=importlib.util.spec_from_file_location('ci_config_check',ROOT/'.ci/check_config.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rules_and_artifact_boundary(tmp_path):
    checker=config_checker()
    assert checker.validate(ROOT/'.gitlab-ci.yml')['gitlab_server_ci_lint'] is False
    config=yaml.safe_load((ROOT/'.gitlab-ci.yml').read_text())
    config['core_test']['artifacts']['paths'].append('.data-process/**')
    unsafe=tmp_path/'unsafe.yml'
    unsafe.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError,match='allowlist'):checker.validate(unsafe)


def test_duplicate_yaml_key_is_not_silently_accepted(tmp_path):
    path=tmp_path/'duplicate.yml'
    path.write_text('workflow: {}\nworkflow: {}\n')
    with pytest.raises(ValueError,match='duplicate'):config_checker().validate(path)


def test_installed_defaults_work_outside_checkout(tmp_path):
    assert (ASSET_ROOT/'definitions/retail_daily.sql').is_file()
    assert json.loads((ASSET_ROOT/'sources/uci-online-retail.json').read_text())['license']=='CC-BY-4.0'
    env={k:v for k,v in os.environ.items() if k not in {'DP_HOME','DP_PROJECT_ROOT','PYTHONPATH'}}
    for args in [('init',),('release',)]:
        result=subprocess.run([sys.executable,'-I','-m','data_process.cli','--home',str(tmp_path/'state'),*args],
                              cwd=tmp_path,env=env,text=True,capture_output=True)
        assert result.returncode==0,result.stderr
    assert len(json.loads(result.stdout)['release_id'])==64


def test_fixed_installed_smoke_uses_no_checkout_or_network(tmp_path):
    out=tmp_path/'report.json'
    result=subprocess.run([sys.executable,'-I','-m','data_process.smoke','--output',str(out)],
                          cwd=tmp_path,text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
    report=json.loads(out.read_text())
    assert report['passed'] and not report['network_used'] and not report['launchd_used']
    assert {r['product'] for r in report['checks']}=={'daily_active','retail_daily'}
    assert 'rows' not in report  # artifact is verification status, not platform data


def test_builder_rejects_false_ci_commit_without_writing_artifact(tmp_path):
    env=dict(os.environ,CI_COMMIT_SHA='0'*40)
    result=subprocess.run([sys.executable,str(ROOT/'.ci/build_wheel.py'),'--out',str(tmp_path/'dist')],
                          cwd=ROOT,env=env,text=True,capture_output=True)
    assert result.returncode!=0 and 'does not match checkout' in result.stderr
    assert not (tmp_path/'dist').exists()
