# data-process

一个本机可运行、可恢复的受控数据交付闭环：合成事件 → 按业务日期统计三省活跃用户 → 独立质量校验 → 发布 → 最近 30 天趋势查询。

Python + DuckDB 1.4.1 + 不可变 Parquet + SQLite 控制状态。定义、release、run、delivery 分离；异步运行、日志、取消、超时、重启核对、同日期幂等替换、审批 CAS、版本回滚和备份恢复均有实际测试。macOS launchd 负责每日触发及 worker 保活；预先批准的固定版本可自动发布。没有网页或公开服务。

```bash
./scripts/setup.sh
.venv/bin/python -m pytest -v
.venv/bin/python scripts/demo.py .data-process/my-demo
./scripts/dp --home .data-process/my-demo trend --end 2026-10-14
```

演示目录必须不存在，不覆盖已有数据。已运行的 30 天演示位于 `.data-process/demo`；每日策略演示位于 `.data-process/live`。全部是合成数据，不含真实凭据。状态、日志和数据默认不进 Git，规范、代码、依赖锁和脱敏验收证据进 Git。

| 阅读入口 | 内容 |
|---|---|
| [业务契约](docs/01-business-contract.md) | 假设、输入输出、边界、R01–R09 验收 |
| [System Map](docs/02-system-map.md) | 职责和关键故障机制 |
| [ADR](docs/adr/001-local-data-product.md) | 官方资料、复用和自研取舍、真实 Iceberg 实验 |
| [追溯表](docs/03-traceability.md) | 需求到代码、测试、证据 |
| [运行手册](docs/04-runbook.md) | 部署、定时、恢复、回滚、权限和生产缺口 |
| [验收报告](docs/evidence/acceptance.md) | 实际环境、命令、结果和未覆盖项 |
| [实施日志](docs/05-implementation-log.md) | 决策变化、失败和修复 |
| [Iceberg 对照实验](experiments/iceberg/README.md) | 无 Spark/Docker 的真实快照验证 |

范围是单用户、小规模本地数据产品，不能等同真实生产平台上线。MySQL/Hive/StarRocks 连接器、真实源水位与权限、多用户隔离、目标容量/SLA、异地灾难恢复仍需上线前完成。Parquet 不等于 Iceberg；轻量 Iceberg 路线已实际验证并记录迁移条件。本机使用 Python sets 独立核对 distinct 口径，不能宣称大数据量自动 out-of-core。
