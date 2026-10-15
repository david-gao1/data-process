"""Independent adversarial checks added after review of the first acceptance suite."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from data_process.core import Platform, ROOT, demo_csv, digest
from data_process.daily import daily
from data_process.operations import emit_alert, flush_alerts, health, heartbeat, monitor, validate_policy
from data_process.worker import worker


@pytest.fixture
def setup(tmp_path):
    p = Platform(tmp_path / 'data#home?space')
    p.init()
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    release = p.release(ROOT / 'definitions/daily_active.sql')
    policy = {'auto_publish': True, 'release_id': release, 'inbox': str(inbox), 'actor': 'review', 'deadline_utc_hour': 8}
    return p, policy


def prepared(setup):
    p, policy = setup
    path = Path(policy['inbox']) / '2026-10-14.csv'
    demo_csv(path, '2026-10-14')
    path.with_suffix('.ready').write_text(digest(path.read_bytes()))
    source = p.ready('2026-10-14', path)
    run = p.submit(policy['release_id'], source, '2026-10-14')
    return p, policy, run


def test_cancel_at_commit_and_late_success_cannot_resurrect(setup):
    p, _, run = prepared(setup)
    worker(p, once=True)
    success = p.run(run)
    assert success['state'] == 'SUCCEEDED' and p.artifact(run).exists()
    # Exact crash/cancel boundary: completed files exist, state commit is not yet successful.
    with p.db(True) as con:
        con.execute("UPDATE runs SET state='RUNNING',output_hash=NULL,report_hash=NULL WHERE id=?", (run,))
    p.cancel(run)
    assert p.finish_run(run, 'SUCCEEDED', 'late child', success['output_hash'], success['report_hash']) == 'CANCELLED'
    assert p.run(run)['output_hash'] is None
    assert p.finish_run(run, 'SUCCEEDED', 'later callback', success['output_hash'], success['report_hash']) == 'CANCELLED'
    with pytest.raises(ValueError, match='successful'):
        p.publish(run, None, 'review', 'late result rejected')
    assert p.trend('2026-10-14')['rows'] == []


def test_interrupted_cannot_accept_late_completion(setup):
    p, _, run = prepared(setup)
    with p.db(True) as con:
        con.execute("UPDATE runs SET state='RUNNING' WHERE id=?", (run,))
    worker(p, once=True)  # no child exists: reconcile unknown result without retry
    assert p.run(run)['state'] == 'INTERRUPTED'
    assert p.finish_run(run, 'SUCCEEDED', 'stale supervisor', 'fake', 'fake') == 'INTERRUPTED'
    assert len(p.runs()) == 1 and not p.audit()


def test_select_boundary_and_external_access(setup, tmp_path):
    p, policy, run = prepared(setup)
    sql = tmp_path / 'bad.sql'
    for text in ('SELECT 1; SELECT 2', "COPY (SELECT 1) TO '/tmp/unwanted-dp-write'", 'INSTALL httpfs', 'CREATE TABLE x(a INT)'):
        sql.write_text(text)
        with pytest.raises(ValueError, match='one SELECT'):
            p.release(sql)
    secret = tmp_path / 'secret.txt'
    secret.write_text('REVIEW_CREDENTIAL_SENTINEL')
    sql.write_text(f"SELECT $business_date AS business_date, '北京' AS province, content AS active_users FROM read_text('{secret}')")
    release = p.release(sql)
    bad = p.submit(release, p.run(run)['source'], '2026-10-14')
    worker(p, once=True)  # normal queued run
    worker(p, once=True)  # external access attempt
    assert p.run(bad)['state'] == 'FAILED'
    log = (p.artifact(bad).parent / 'run.log').read_text()
    assert 'disabled' in log.lower() and 'REVIEW_CREDENTIAL_SENTINEL' not in log
    with pytest.raises(ValueError, match='not found'):
        p.artifact('../../outside')


def test_manifest_file_tamper_and_child_environment(setup, monkeypatch):
    p, policy, run = prepared(setup)
    captured = []
    real = subprocess.Popen
    def spy(*args, **kwargs):
        captured.append(kwargs['env'])
        return real(*args, **kwargs)
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'REVIEW_ENV_SENTINEL')
    monkeypatch.setenv('MYSQL_PASSWORD', 'REVIEW_DB_SENTINEL')
    monkeypatch.setattr('data_process.worker.subprocess.Popen', spy)
    worker(p, once=True)
    assert p.run(run)['state'] == 'SUCCEEDED'
    assert captured and all(set(env) == {'PATH', 'PYTHONUNBUFFERED'} for env in captured)
    manifest = p.home / 'releases' / policy['release_id'] / 'manifest.json'
    manifest.write_text('{}')
    with pytest.raises(ValueError, match='manifest file'):
        p.publish(run, None, 'review', 'must reject tampered manifest')


@pytest.mark.parametrize('change', [
    {'unexpected': 'x'}, {'enabled': 'false'}, {'actor': ''}, {'inbox': 'relative'},
    {'timeout': float('nan')}, {'deadline_utc_hour': 24}, {'through_date': 123},
    {'alerts': {'sink': 'webhook'}}, {'alerts': {'enabled': 'yes'}}, {'alerts': {'events': ['unknown']}}
])
def test_strict_config_validation(setup, change):
    p, config = setup
    config.update(change)
    with pytest.raises(ValueError):
        validate_policy(p, config)
    assert not p.runs()


def test_missing_ready_and_overdue_local_notifications_are_deduplicated(setup):
    p, config = setup
    for _ in range(2):
        with pytest.raises(FileNotFoundError):
            daily(p, config, '2026-10-14')
    now = datetime(2026, 10, 15, 9, tzinfo=timezone.utc)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: monitor(p, config, now), range(3)))
    assert all(r['delivery']['state'] == 'overdue' and not r['delivery']['ready_files_present'] for r in results)
    paths = list((p.home / 'notifications').glob('*.json'))
    assert len(paths) == 3  # one failure, one overdue, one worker incident per business date
    events = {json.loads(f.read_text())['event'] for f in paths}
    assert events == {'daily_failed', 'delivery_overdue', 'worker_unhealthy'}
    assert health(p, config, now)['delivery']['last_attempt']['code'] == 'input_not_ready'
    assert not p.runs() and not p.audit()


def test_notification_delivery_recovers_after_disk_write_failure(setup, monkeypatch):
    p, _ = setup
    import data_process.operations as operations
    original = operations.durable_write
    monkeypatch.setattr(operations, 'durable_write', lambda *_: (_ for _ in ()).throw(OSError('disk failure')))
    with pytest.raises(OSError):
        emit_alert(p, 'run_failed', 'review-run', 'FAILED')
    assert health(p)['pending_notifications'] == 1
    monkeypatch.setattr(operations, 'durable_write', original)
    assert flush_alerts(p) == 1
    assert health(p)['pending_notifications'] == 0
    emit_alert(p, 'run_failed', 'review-run', 'FAILED')
    assert len(list((p.home / 'notifications').glob('*.json'))) == 1


def test_expired_demo_policy_skips_future_input_without_failure_alert(setup):
    p, config = setup
    config['through_date'] = '2026-10-14'
    result = daily(p, config, '2026-10-15')
    assert result['state'] == 'disabled_or_expired'
    config['alerts'] = {'enabled': False}
    emit_alert(p, 'daily_failed', 'test', 'ignored', config)
    assert not (p.home / 'notifications').exists()
    assert not p.runs()


def test_heartbeat_and_stale_owner_cannot_clobber_restarted_worker(setup):
    p, _ = setup
    heartbeat(p, 'old')
    assert health(p)['worker']['alive']
    heartbeat(p, 'new')
    heartbeat(p, 'old', 'stopped')
    assert health(p)['worker']['alive']
    heartbeat(p, 'new', 'stopped')
    assert not health(p)['worker']['alive']


def test_concurrent_daily_triggers_share_run_and_delivery(setup):
    p, config, _ = prepared(setup)
    child = subprocess.Popen([sys.executable, '-m', 'data_process.cli', '--home', str(p.home), 'worker'],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: daily(p, config, '2026-10-14', 15), range(2)))
        assert len({r['run_id'] for r in results}) == 1
        assert len(p.audit()) == 1
        assert len(p.trend('2026-10-14')['rows']) == 3
        assert len(p.runs()) == 2  # one explicit fixture run + one shared daily run
        with p.db() as con:
            assert con.execute("SELECT COUNT(*) FROM notifications WHERE payload LIKE '%daily_failed%'").fetchone()[0] == 0
    finally:
        child.terminate()
        child.communicate(timeout=10)


def test_delivery_and_audit_are_one_transaction_on_injected_failure(setup):
    import sqlite3
    p, policy, first = prepared(setup)
    worker(p, once=True)
    p.publish(first, None, 'review', 'baseline')
    second = p.submit(policy['release_id'], p.run(first)['source'], '2026-10-14')
    worker(p, once=True)
    with p.db(True) as con:
        con.execute("CREATE TRIGGER review_fail_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'injected audit failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='injected'):
        p.publish(second, first, 'review', 'must roll back pointer too')
    assert len(p.audit()) == 1
    assert all(r['run_id'] == first for r in p.trend('2026-10-14')['rows'])
    with p.db(True) as con:
        con.execute('DROP TRIGGER review_fail_audit')
    p.publish(second, first, 'review', 'retry explicit operator publication')
    assert len(p.audit()) == 2
    assert all(r['run_id'] == second for r in p.trend('2026-10-14')['rows'])


def test_backup_preserves_queued_and_cancelled_without_reexecuting(setup, tmp_path):
    import shutil
    p, policy, queued = prepared(setup)
    cancelled = p.submit(policy['release_id'], p.run(queued)['source'], '2026-10-14')
    p.cancel(cancelled)
    destination = tmp_path / 'backup'
    p.backup(destination)
    restored = Platform(destination)
    assert restored.check()['integrity'] == 'ok'
    assert restored.run(cancelled)['state'] == 'CANCELLED'
    worker(restored, once=True)
    assert restored.run(queued)['state'] == 'SUCCEEDED'
    assert p.run(queued)['state'] == 'QUEUED'  # restoration does not touch the original
    assert restored.run(cancelled)['state'] == 'CANCELLED'
    assert not restored.audit() and restored.trend('2026-10-14')['rows'] == []


def test_cli_respects_disabled_local_alerts_on_missing_input(setup, tmp_path):
    p, config = setup
    config['alerts'] = {'enabled': False}
    path = tmp_path / 'policy.json'
    path.write_text(json.dumps(config))
    result = subprocess.run([sys.executable, '-m', 'data_process.daily', '--home', str(p.home),
                             '--config', str(path), '--date', '2026-10-14'], capture_output=True, text=True)
    assert result.returncode == 2
    with p.db() as con:
        assert con.execute('SELECT COUNT(*) FROM notifications').fetchone()[0] == 0
    assert not p.runs()
