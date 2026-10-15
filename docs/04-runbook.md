# 运行与恢复手册

本版支持 macOS 单用户、本地磁盘、可信操作员、小规模 CSV；所有附带数据均为合成演示。无网络服务、无需 Docker。

## 可重复部署

Python 3.10–3.12、uv、git。实测 Python 3.11.8 / DuckDB 1.4.1 / macOS arm64。从项目根目录：

```bash
./scripts/setup.sh
./scripts/dp init
.venv/bin/python -m pytest -v
.venv/bin/python scripts/demo.py .data-process/my-new-demo
./scripts/dp --home .data-process/my-new-demo trend --end 2026-10-14
```

setup 使用 uv.lock（含包 hash）与普通安装；本机可编辑 `.pth` 曾被环境自动隐藏导致 Python 忽略，普通安装不依赖 `.pth`。修改源码后重新 setup，再启动 worker。`scripts/dp` 自动进入项目根，支持从任意目录调用；直接 `.venv/bin/dp` 或 `python -m` 时需在项目根执行，或设置 `DP_PROJECT_ROOT`。重新安装不会覆盖旧 release；旧 run 的计算使用自己的快照，Python/DuckDB 运行时不一致会拒绝执行。

## 人工审批闭环

```bash
./scripts/dp demo-source --date 2026-10-14 --output /tmp/dp-events-new.csv
./scripts/dp ready --date 2026-10-14 --file /tmp/dp-events-new.csv
./scripts/dp release
# 记录以上返回的 SOURCE 和 RELEASE；此处是占位符，替换为真实返回值。
./scripts/dp submit --date 2026-10-14 --source SOURCE --release RELEASE --timeout 60 --key operator-request-001
./scripts/dp worker
# 另一终端：
./scripts/dp status RUN
./scripts/dp logs RUN
./scripts/dp inspect RUN
./scripts/dp publish RUN --expected NONE --actor operator --reason '已核对三省口径和数据'
./scripts/dp trend --end 2026-10-14
```

首次发布 `--expected NONE`，替换必须提供当前 run，避免并发审批覆盖；重复同一发布且 expected 为自身时不新增审计。操作员纠正输入应重新 ready 创建新 source，重新 submit 得新 run。相同 key 与参数返回同一实例，不能用同一 key 改参数。

## 每日自动交付

两个项目内 LaunchAgent plist：worker 由 launchd KeepAlive；daily 每天系统本地时间 08:00 执行一次，业务日期始终取 UTC 昨日。此时间是演示默认值，可改生成脚本；它不是经业务签字的 SLA。系统本地时区应在部署时核实；睡眠、退出登录、停机可能延迟或漏跑，不承诺补齐所有历史日期。

daily policy 固定 `release_id`、`inbox`、actor、timeout，必须显式 `auto_publish: true`。上游将 `YYYY-MM-DD.csv` 完整导出后，原子落盘同名 `.ready`，内容为该 CSV 的 SHA256；不得先 ready 后改数据。daily 验证摘要，固定快照，提交持久 run，等待 worker 校验，仅在成功后按批准策略自动发布并记审计。缺输入、错误 ready、失败/取消/超时、冲突均退出非零；不自动重试。幂等重放不会新增交付，已经被人工替换的旧任务不会覆盖人工结果。

```bash
# 显式创建合成演示 inbox 与固定版本自动发布策略；不连接真实源：
.venv/bin/python scripts/prepare_demo_policy.py
.venv/bin/python scripts/configure_launchd.py --home .data-process/live --config .data-process/live/daily-policy.json
plutil -lint .data-process/launchd/*.plist
launchctl bootstrap gui/$(id -u) .data-process/launchd/local.data-process.worker.plist
launchctl bootstrap gui/$(id -u) .data-process/launchd/local.data-process.daily.plist
launchctl kickstart gui/$(id -u)/local.data-process.daily
launchctl print gui/$(id -u)/local.data-process.daily
./scripts/dp --home .data-process/live trend --end 2026-10-14
```

plist 保存在项目内；登录域加载仅适用于当前登录会话。退出登录/重启后使用上述 bootstrap 恢复，重复加载先 bootout。若需要重启自动注册，安装到用户 LaunchAgents 或使用受管服务账号是单独的部署步骤，本次未修改用户 Library。无人登录生产机器使用运维批准的 LaunchDaemon/systemd，不能把当前登录会话当 HA。

```bash
# 变更/卸载，先 daily 后 worker，操作不会删除数据：
launchctl bootout gui/$(id -u)/local.data-process.daily
launchctl bootout gui/$(id -u)/local.data-process.worker
```

生产上游连接器未实现；当前 live inbox 只有合成日期，未来日期没有输入会明确失败。这是有意暴露的数据就绪状态，不能靠自动造数掩盖。定时链路验证用 kickstart 执行与日历相同命令；未等待真实次日 08:00。

## 故障恢复

- 取消：`scripts/dp cancel RUN`。QUEUED 立即取消；RUNNING 标 CANCELLING，由存活 worker 对本地子进程 terminate/kill/wait 后确认。worker 不在时重启核对。仅适用本版固定 SQL 子进程，不能保证远程引擎停止。
- 超时：提交 timeout 0.1–3600 秒，worker 对当前进程硬终止并 wait；不发布。
- worker 崩溃：重启 worker，继承锁与父进程 guard 防止幸存计算与新 worker 重叠；旧 RUNNING 标 INTERRUPTED。未知候选不得发布，人工检查日志后新建 run；队列保留，不盲目重试。
- 回滚：`scripts/dp rollback OLD_RUN --expected CURRENT_RUN --actor operator --reason '回退原因'`，仅历史已发布且文件摘要校验通过的成功版本可回滚。不会重算，不会覆盖候选。
- 损坏：`scripts/dp check` 检查 SQLite、外键、全部输入、release、成功产物。正式读取也校验产物摘要，损坏拒绝交付。不要篡改数据库状态伪造成功。
- 磁盘满/权限错误：保留状态和日志，释放空间后重启核对，明确重提；未引用文件不自动清理，避免误删回滚依据。

## 备份、恢复与保留

先停止 daily 和 worker；`scripts/dp worker --once` 可先核对中断任务，但会处理最多一个排队任务。确认无运行态后：

```bash
./scripts/dp --home .data-process/live backup /tmp/dp-backup-new
# 不覆盖现有目录：
cp -R /tmp/dp-backup-new /tmp/dp-restored-new
./scripts/dp --home /tmp/dp-restored-new check
./scripts/dp --home /tmp/dp-restored-new trend --end 2026-10-14
```

backup 持有 worker 锁与 SQLite 写事务，排除并发运行与控制写入后复制整个 home；目标必须全新且在 home 外。restore 不复用旧绝对 spec，后续新 run 会按新 home 生成路径。daily policy 中 inbox 是绝对路径，恢复/迁移后必须同步调整配置并重新生成 plist。实测本机复制恢复、历史版本回滚；异机灾难恢复、真实断电不在已验证范围。

不自动删除 sources/releases/candidates/audit；备份应包括全部目录、源 Git commit 和运行环境。快照不是备份，本机副本不是异地备份。真实上线定义保留期、容量告警和异地备份后再增加经过引用校验的 GC。

## 权限和生产边界

home 0700，umask 077，CLI 不存云凭据，计算子进程不继承云/数据库环境变量，SQL 读取快照后关闭外部访问。所有操作是同一个可信 OS 用户，actor 是审计标签，不是认证；正式查询以只读 SQLite 打开，但相同用户可改底层文件。真实多人使用必须用独立服务账号和只读消费身份、认证授权与独立发布审批，不能把命令参数当 RBAC。

上线前路径：实现 MySQL/Hive/StarRocks 只读导出及源水位校验 → 业务口径/时区/零活跃/迟到数据签字 → 安全账号/凭据托管 → 目标环境容量与故障测试 → SLA/告警/值守 → 异地恢复演练。需要多引擎共享表时迁移 Iceberg catalog 和持久对象存储；需要 DAG/自动重试时接入现成编排器并撤掉本地队列。不得将本机演示通过描述为真实生产验收完成。
