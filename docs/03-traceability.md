# 需求、代码、验收追溯

需求源为 [业务契约](01-business-contract.md)，判断依据为 [ADR](adr/001-local-data-product.md)。

| ID | 责任代码 | 可执行 Harness / 通过判据 |
|---|---|---|
| R01 | core.ready/submit/trend、compute.calculate、cli、scripts/demo.py | test_normal_rerun_version_rollback_and_cas、test_30_day_window_and_missing_not_zero；CLI demo 30 天 90 行 |
| R02 | compute.calculate、core.submit | test_bad_input_blocks_publication（5 组）、test_not_ready_invalid_dates_and_numbers、test_quality_catches_wrong_sql |
| R03 | core.submit/publish | test_normal_rerun_version_rollback_and_cas、test_concurrent_idempotent_submit_and_publication；日期唯一 delivery，重复 key 一个 run |
| R04 | core.release/verify_release、worker 的固定代码快照、cli.inspect | normal_rerun 中修改定义产生新 hash；tamper_detected 中篡改发布阻止执行 |
| R05 | core.cancel、worker.stop_process/超时状态提交 | test_cancel_queued_and_running_and_timeout；真实 Popen terminate/kill/wait |
| R06 | worker flock/重启对账、compute 父进程 guard | test_sigkill_restart_reconciles_and_preserves_queue、test_single_worker_lock_and_graceful_stop |
| R07 | core.publish、SQLite delivery/audit 事务 | normal_rerun 回滚及 CAS；concurrent_publication 只能一个提交 |
| R08 | core.verify_artifact/check/backup | test_tamper_detected_at_source_release_delivery、test_backup_restore_and_history |
| R09 | daily.daily、configure_launchd.py、原生 launchd | test_daily_automatic_policy_and_replay；真实 bootstrap/kickstart + 日历注册，见验收报告 |

总闸门：`./scripts/setup.sh` → `.venv/bin/python -m pytest -v` → `.venv/bin/python scripts/demo.py 新目录` → 真实 launchd 触发 → check/backup/restore。测试与演示不依赖网络或真实数据库。依赖安装首次需网络。测试的故障状态是本地 SQL 子进程事实，不外推到 Spark、Hive 或数据库远程取消。
