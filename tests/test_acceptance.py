"""Contract acceptance: real OS workers, DuckDB execution, Parquet and SQLite."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import pytest

from data_process.core import Platform, ROOT, demo_csv

DAY = "2026-10-14"


@pytest.fixture
def product(tmp_path):
    p = Platform(tmp_path / "state")
    p.init()
    source_file = tmp_path / "events.csv"
    demo_csv(source_file, DAY)
    source = p.ready(DAY, source_file)
    release = p.release(ROOT / "definitions/daily_active.sql")
    return p, release, source


def submit(product, **kwargs):
    p, release, source = product
    return p.submit(release, source, DAY, **kwargs)


def launch(p, once=True):
    return subprocess.Popen([sys.executable, "-m", "data_process.cli", "--home", str(p.home),
                             "worker", *(["--once"] if once else [])],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def finish(p):
    child = launch(p)
    out, _ = child.communicate(timeout=15)
    assert child.returncode == 0, out
    return out


def await_state(p, run, states, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        row = p.run(run)
        if row["state"] in states:
            return row
        time.sleep(0.03)
    pytest.fail(f"state deadline: {p.run(run)}")


def approve(p, run, expected=None, rollback=False):
    return p.publish(run, expected, "test-operator", "acceptance review", rollback)


def test_normal_rerun_version_rollback_and_cas(product, tmp_path):
    p, release, source = product
    first = submit(product, key="request-1")
    assert submit(product, key="request-1") == first
    assert p.run(first)["state"] == "QUEUED"
    assert p.trend(DAY)["rows"] == []
    with pytest.raises(ValueError, match="successful"):
        approve(p, first)
    finish(p)
    assert p.run(first)["state"] == "SUCCEEDED"
    assert p.trend(DAY)["rows"] == []  # success alone is not a publication
    approve(p, first)
    trend = p.trend(DAY)
    assert len(trend["missing_dates"]) == 29
    assert {r["province"]: r["active_users"] for r in trend["rows"]} == {"北京": 3, "上海": 4, "广东": 5}
    assert all(r["run_id"] == first and r["release_id"] == release for r in trend["rows"])
    changed = tmp_path / "changed.sql"
    changed.write_text((ROOT / "definitions/daily_active.sql").read_text() + "\n-- reviewed v2\n")
    second_release = p.release(changed)
    assert second_release != release
    assert p.release(changed) == second_release
    second = p.submit(second_release, source, DAY)
    finish(p)
    with pytest.raises(ValueError, match="conflict"):
        approve(p, second)
    approve(p, second, first)
    assert len(p.trend(DAY)["rows"]) == 3
    assert all(r["run_id"] == second for r in p.trend(DAY)["rows"])
    approve(p, first, second, rollback=True)
    assert all(r["run_id"] == first for r in p.trend(DAY)["rows"])
    assert [r["action"] for r in p.audit()] == ["publish", "publish", "rollback"]
    assert approve(p, first, first)["changed"] is False
    assert p.check()["integrity"] == "ok"
    with pytest.raises(ValueError, match="conflict"):
        submit(product, key="request-1", timeout=2)


@pytest.mark.parametrize("data", [
    "business_date,user_id,province\n2026-10-13,u,北京\n",
    "business_date,user_id,province\n2026-10-14,,北京\n",
    "business_date,user_id,province\n2026-10-14,u,火星\n",
    "business_date,user_id,province\n2026-10-14,u,北京\n",
    "wrong,columns\na,b\n",
])
def test_bad_input_blocks_publication(product, tmp_path, data):
    p, release, _ = product
    bad = tmp_path / "bad.csv"
    bad.write_text(data)
    source = p.ready(DAY, bad)
    run = p.submit(release, source, DAY)
    finish(p)
    assert p.run(run)["state"] == "FAILED"
    assert "ValueError" in (p.artifact(run).parent / "run.log").read_text()
    with pytest.raises(ValueError, match="successful"):
        approve(p, run)
    assert not p.trend(DAY)["rows"]


def test_not_ready_invalid_dates_and_numbers(product):
    p, release, source = product
    for day in ("2026-02-30", "20261014", "2026-1-01"):
        with pytest.raises(ValueError):
            p.submit(release, source, day)
    with pytest.raises(ValueError, match="not ready"):
        p.submit(release, "missing", DAY)
    with pytest.raises(ValueError, match="not ready"):
        p.submit(release, source, "2026-10-13")
    for timeout in (float("nan"), float("inf"), -1):
        with pytest.raises(ValueError):
            submit(product, timeout=timeout)


def test_quality_catches_wrong_sql(product, tmp_path):
    p, _, source = product
    wrong = tmp_path / "wrong.sql"
    wrong.write_text("SELECT business_date, province, COUNT(*)::BIGINT AS active_users FROM events WHERE business_date=$business_date GROUP BY business_date,province")
    release = p.release(wrong)
    run = p.submit(release, source, DAY)
    finish(p)
    assert p.run(run)["state"] == "FAILED"
    assert "independent distinct-user oracle" in (p.artifact(run).parent / "run.log").read_text()


def test_cancel_queued_and_running_and_timeout(product):
    p, _, _ = product
    queued = submit(product)
    p.cancel(queued)
    assert p.run(queued)["state"] == "CANCELLED"
    running = submit(product, delay=10)
    child = launch(p)
    try:
        await_state(p, running, {"RUNNING"})
        p.cancel(running)
        out, _ = child.communicate(timeout=10)
        assert child.returncode == 0, out
        assert p.run(running)["state"] == "CANCELLED"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    timed = submit(product, timeout=0.2, delay=10)
    finish(p)
    assert p.run(timed)["state"] == "TIMED_OUT"
    for run in (queued, running, timed):
        with pytest.raises(ValueError, match="successful"):
            approve(p, run)


def test_sigkill_restart_reconciles_and_preserves_queue(product):
    p, _, _ = product
    interrupted = submit(product, delay=10)
    queued = submit(product)
    child = launch(p, once=False)
    try:
        await_state(p, interrupted, {"RUNNING"})
        # Wait for child start / candidate creation, then kill actual supervisor.
        deadline = time.monotonic() + 5
        while not (p.artifact(interrupted).parent / "run.log").exists():
            assert time.monotonic() < deadline
            time.sleep(0.02)
        child.kill()
        child.communicate(timeout=10)
        # Orphan guard releases inherited lock; retry starting a worker, never the run.
        deadline = time.monotonic() + 10
        while True:
            replacement = launch(p)
            out, _ = replacement.communicate(timeout=15)
            if replacement.returncode == 0:
                break
            assert "holds the lock" in out
            assert time.monotonic() < deadline
            time.sleep(0.1)
        assert p.run(interrupted)["state"] == "INTERRUPTED"
        assert p.run(queued)["state"] == "SUCCEEDED"
        assert p.trend(DAY)["rows"] == []
        assert "reconciliation" in p.run(interrupted)["message"]
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_single_worker_lock_and_graceful_stop(product):
    p, _, _ = product
    run = submit(product, delay=10)
    child = launch(p, once=False)
    try:
        await_state(p, run, {"RUNNING"})
        duplicate = launch(p)
        out, _ = duplicate.communicate(timeout=10)
        assert duplicate.returncode == 2 and "holds the lock" in out
        with pytest.raises(BlockingIOError):
            p.backup(p.home.parent / "busy-backup")
        child.terminate()
        child.communicate(timeout=10)
        assert p.run(run)["state"] == "INTERRUPTED"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_tamper_detected_at_source_release_delivery(product):
    p, release, source = product
    run = submit(product)
    source_path = p.home / "sources" / f"{source}.csv"
    original = source_path.read_bytes()
    source_path.write_bytes(original + b"corrupt")
    finish(p)
    assert p.run(run)["state"] == "FAILED"
    source_path.write_bytes(original)
    good = submit(product)
    finish(p)
    approve(p, good)
    output = p.artifact(good)
    output.write_bytes(output.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="checksum"):
        p.trend(DAY)
    with pytest.raises(ValueError, match="checksum"):
        p.check()
    definition = p.home / "releases" / release / "definition.sql"
    definition.write_text("SELECT 0")
    with pytest.raises(ValueError, match="checksum"):
        submit(product)


def test_backup_restore_and_history(product, tmp_path):
    p, _, _ = product
    first = submit(product)
    finish(p)
    approve(p, first)
    second = submit(product)
    finish(p)
    approve(p, second, first)
    backup = tmp_path / "backup"
    p.backup(backup)
    restored_path = tmp_path / "restored"
    shutil.copytree(backup, restored_path)
    restored = Platform(restored_path)
    assert restored.check()["integrity"] == "ok"
    assert restored.trend(DAY) == p.trend(DAY)
    approve(restored, first, second, rollback=True)
    assert restored.trend(DAY)["rows"][0]["run_id"] == first
    assert p.trend(DAY)["rows"][0]["run_id"] == second


def test_concurrent_idempotent_submit_and_publication(product):
    p, _, _ = product
    with ThreadPoolExecutor(max_workers=4) as pool:
        runs = list(pool.map(lambda _: submit(product, key="parallel"), range(8)))
    assert len(set(runs)) == 1
    finish(p)
    other = submit(product)
    finish(p)
    def attempt(run):
        try:
            approve(p, run)
            return "published"
        except ValueError:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, [runs[0], other]))
    assert sorted(outcomes) == ["conflict", "published"]
    assert len(p.audit()) == 1
    assert len(p.trend(DAY)["rows"]) == 3


def test_30_day_window_and_missing_not_zero(product, tmp_path):
    p, release, _ = product
    for day in ("2026-09-14", "2026-09-15", DAY):
        file = tmp_path / f"{day}.csv"
        demo_csv(file, day)
        source = p.ready(day, file)
        run = p.submit(release, source, day)
        finish(p)
        approve(p, run)
    trend = p.trend(DAY)
    assert trend["start"] == "2026-09-15"
    assert len(trend["rows"]) == 6 and len(trend["missing_dates"]) == 28
    assert all(r["business_date"] >= trend["start"] for r in trend["rows"])


def test_daily_automatic_policy_and_replay(product, tmp_path):
    from data_process.core import digest
    from data_process.daily import daily
    p, release, _ = product
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    path = inbox / f"{DAY}.csv"
    demo_csv(path, DAY)
    path.with_suffix(".ready").write_text(digest(path.read_bytes()))
    config = {"auto_publish": True, "release_id": release, "inbox": str(inbox), "actor": "daily-policy"}
    child = launch(p, once=False)
    try:
        first = daily(p, config, DAY, 15)
        second = daily(p, config, DAY, 15)
        assert first["run_id"] == second["run_id"]
        assert second["state"] == "already_delivered"
        assert len(p.audit()) == 1 and len(p.trend(DAY)["rows"]) == 3
        manual = submit(product)
        await_state(p, manual, {"SUCCEEDED"})
        approve(p, manual, first["run_id"])
        with pytest.raises(ValueError, match="superseded"):
            daily(p, config, DAY, 15)
        path.with_suffix(".ready").write_text("bad checksum")
        with pytest.raises(ValueError, match="checksum"):
            daily(p, config, DAY, 15)
        config["auto_publish"] = False
        with pytest.raises(ValueError, match="explicit"):
            daily(p, config, DAY, 15)
    finally:
        child.terminate()
        child.communicate(timeout=10)
