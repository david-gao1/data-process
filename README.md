# data-process

一个本机可运行、可恢复的受控数据交付平台。已完成两条业务闭环：合成事件的三省活跃用户统计，以及UCI公开真实零售交易的每日国家开票/取消净额。两者都经过独立质量校验、受控发布和正式查询。

Python + DuckDB 1.4.1 + 不可变 Parquet + SQLite 控制状态。定义、release、run、delivery 分离；异步运行、日志、取消、超时、重启核对、同日期幂等替换、审批 CAS、版本回滚和备份恢复均有实际测试。macOS launchd 负责每日触发、worker 保活与每小时健康检查；预先批准的固定版本可自动发布。现已增加本机只读管理门户；没有公开服务。

```bash
./scripts/setup.sh
.venv/bin/python -m pytest -v
.venv/bin/python scripts/demo.py .data-process/my-demo
./scripts/dp --home .data-process/my-demo trend --end 2026-10-14
```

演示目录必须不存在，不覆盖已有数据。已运行的 30 天演示位于 `.data-process/demo`；每日策略演示位于 `.data-process/live`。以上三省目录是合成数据；新增 `.data-process/retail` 保存许可明确的公开真实历史数据，不含连接凭据。状态、日志和数据默认不进 Git，规范、代码、依赖锁和脱敏验收证据进 Git。

| 阅读入口 | 内容 |
|---|---|
| [公开零售验收](docs/evidence/retail-acceptance.md) | 真实来源、两个历史批次、45项测试、独立对账 |
| [零售字典与命令](docs/09-retail-dictionary-runbook.md) | 开票/取消口径、原始版本、数据字典与恢复 |
| [零售业务契约](docs/08-public-retail-contract.md) | 下载边界、数据质量、隐私裁剪与验收 |
| [业务契约](docs/01-business-contract.md) | 假设、输入输出、边界、R01–R09 验收 |
| [System Map](docs/02-system-map.md) | 职责和关键故障机制 |
| [ADR](docs/adr/001-local-data-product.md) | 官方资料、复用和自研取舍、真实 Iceberg 实验 |
| [追溯表](docs/03-traceability.md) | 需求到代码、测试、证据 |
| [运行手册](docs/04-runbook.md) | 部署、定时、恢复、回滚、权限和生产缺口 |
| [验收报告](docs/evidence/acceptance.md) | 实际环境、命令、结果和未覆盖项 |
| [质量审查](docs/07-quality-review.md) | 38项回归、竞态修复、健康与本地告警 |
| [生产接入问题](docs/06-production-handoff.md) | 必须提供的真实环境与业务信息 |
| [实施日志](docs/05-implementation-log.md) | 决策变化、失败和修复 |
| [Iceberg 对照实验](experiments/iceberg/README.md) | 无 Spark/Docker 的真实快照验证 |

范围是单用户、小规模本地数据产品，不能等同真实生产平台上线。MySQL/Hive/StarRocks 连接器、真实源水位与权限、多用户隔离、目标容量/SLA、异地灾难恢复仍需上线前完成。Parquet 不等于 Iceberg；轻量 Iceberg 路线已实际验证并记录迁移条件。本机使用 Python sets 独立核对 distinct 口径，不能宣称大数据量自动 out-of-core。

运行状态：`./scripts/dp --home .data-process/live health --config .data-process/live/daily-policy.json`。本地通知位于状态目录的 `notifications/`；没有外部消息发送。`./scripts/services.sh start|stop|restart|status` 管理项目的用户登录域作业。附带合成策略有截止日期，过期后跳过；真实上线问题见生产接入文档。


查询本次已经发布的公开真实历史产品：

```bash
./scripts/dp --home .data-process/retail trend --end 2011-01-31
./scripts/dp --home .data-process/retail check
```

来源：Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5BW33 ，CC BY 4.0。它是2010–2011静态真实交易快照；2010-12和2011-01是历史批次回放，不能称实时CDC。正式交付只含日国家聚合，不含CustomerID/订单编号/原始记录。公开接入是有限显式命令，没有把现有演示作业改成自动外网下载。

GitLab 已完成本机私有项目与受限 Shell Runner 接入，三项真实 CI（核心测试、commit 绑定 wheel、独立安装验证）通过；见 [CI/CD 手册](docs/10-gitlab-ci-runbook.md)和[接入验收](docs/evidence/gitlab/runner-2026-10-18/README.md)。GitHub 与本机 GitLab 的 main 按当次授权同步；UCI 网络回放仍为显式手动作业，未部署应用。

下一阶段：以“数据运行 + 研发交付”的只读统一门户体验 DevOps。已完成[官方资料调研](docs/research/2026-10-18-gitlab-devops.md)和[项目落地路线](docs/11-devops-visual-console-roadmap.md)；门户、Web API、软件部署与新增权限仍处于设计阶段。

只读统一门户：参见[运行手册](docs/12-console-runbook.md)。五个视图整合业务运行与研发交付；默认仅本机、先接专用合成环境。GitLab实时摘要使用单独批准的只读身份，未配置时明确显示未连接。
