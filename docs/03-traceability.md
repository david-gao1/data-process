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

## 独立质量审查新增

| ID | 代码与测试 | 新判据 |
|---|---|---|
| R05/R06加强 | core.finish_run；test_cancel_at_commit_and_late_success_cannot_resurrect、test_interrupted_cannot_accept_late_completion | 已存在结果文件也不能越过取消或中断终态 |
| R07加强 | test_delivery_and_audit_are_one_transaction_on_injected_failure | SQLite trigger注入审计失败，指针和审计都回滚 |
| R09加强 | test_concurrent_daily_triggers_share_run_and_delivery | 同时触发一个daily run/一个发布，无虚假失败告警 |
| R08加强 | test_backup_preserves_queued_and_cancelled_without_reexecuting | 备份还原保留队列和取消，原目录不变 |
| R10 | operations、CLI health/monitor/config-check、launchd monitor | 严格配置、心跳、截止检查、缺ready可见、到期跳过、事务本地通知去重/恢复；tests/test_review.py和scripts/verify_operations.py |
| R11 | core.release/verify_release、worker最小环境 | 单SELECT、阻止外部读取、manifest篡改拒绝，云/数据库测试凭据不传子进程 |


## 公开真实零售产品

[业务契约P01–P07](08-public-retail-contract.md) → public_retail（有界下载、xlsx schema与Decimal规范化、来源manifest） → retail_compute与definitions/retail_daily.sql（独立整数oracle） → core注册产品/通用查询（worker和publish事务复用） → tests/test_public_retail.py（7个故障/业务case）与scripts/retail_e2e.py（真实两月、231国家日、发布恢复和备份核对） → [原始验收证据](evidence/retail-acceptance.md)。
