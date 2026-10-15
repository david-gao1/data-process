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

首次发布 `--expected NONE`，替换必须提供当前 run，避免并发审批覆盖；当前指针已是目标run时幂等返回，不新增审计或覆盖数据。操作员纠正输入应重新 ready 创建新 source，重新 submit 得新 run。相同 key 与参数返回同一实例，不能用同一 key 改参数。

## 每日自动交付

三个项目内 LaunchAgent plist（独立审查后加入monitor）：worker 由 launchd KeepAlive；daily 每天系统本地时间 08:00 执行一次，业务日期始终取 UTC 昨日。此时间是演示默认值，可改生成脚本；它不是经业务签字的 SLA。系统本地时区应在部署时核实；睡眠、退出登录、停机可能延迟或漏跑，不承诺补齐所有历史日期。

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

## 独立审查后新增：配置、健康和本地告警

更新源码后运行 setup，并重新加载 worker；worker 启动自动幂等建立 operational_status 和 notifications 表，兼容旧home。更换固定版本需要显式准备并审核策略，不会覆盖旧 release。

```bash
./scripts/dp --home .data-process/live config-check --config .data-process/live/daily-policy.json
./scripts/dp --home .data-process/live health --config .data-process/live/daily-policy.json
./scripts/dp --home .data-process/live monitor --config .data-process/live/daily-policy.json
./scripts/dp --home .data-process/live notifications
.venv/bin/python scripts/verify_operations.py .data-process/new-ops-proof
```

health 显示worker心跳（10秒阈值）、状态计数、最老队列年龄、超过timeout+5秒仍非终态的run、待投递告警和UTC昨日交付状态；不健康退出1。check 检查数据完整性，health 检查运行活性，两者都要看。

policy 允许字段：auto_publish、release_id、inbox、actor、timeout、enabled、through_date、deadline_utc_hour、alerts，未知字段或错误类型拒绝。inbox 必须是已存在的绝对路径。默认deadline UTC08:00仅是可配置参考，需业务确认。`enabled:false` 停用每日业务处理；`through_date` 为最后允许业务日期。附带 prepare_demo_policy 只生成截至UTC昨日的合成策略，明天起daily成功返回 disabled_or_expired，不反复报缺输入。要持续生产，需要真实上游或显式更新演示期，不自动造数。

alerts 示例：`{"sink":"local","enabled":true,"events":["run_failed","daily_failed","delivery_overdue","worker_unhealthy"]}`。仅支持local，不接受webhook/命令字符串。worker 使用 `--policy` 加载相同配置；不带策略时默认所有本地事件开启。配置无效时发本地配置错误记录，避免配置错误让故障完全不可见。

通知先事务写 notifications outbox，后写 home/notifications/<SHA256>.json，只有成功fsync落盘后标delivered。失败保留待投递，由重启worker或monitor重放。run失败按run去重，daily失败/交付逾期/worker异常各按业务日期去重；重复缺输入、反复monitor不会每次新增文件。内容只有事件、范围、原因码和时间，不包含异常原文、SQL、配置、数据行或凭据。文件是本地可验证通知落点，没有实际发送到人；生产需批准并接入现有监控/值班渠道。

configure_launchd 现在还生成 `local.data-process.monitor.plist`，用户登录域每3600秒执行一次，无KeepAlive重试；daily也无失败自动重试。加载和停用：

```bash
launchctl bootstrap gui/$(id -u) .data-process/launchd/local.data-process.monitor.plist
launchctl kickstart gui/$(id -u)/local.data-process.monitor
launchctl bootout gui/$(id -u)/local.data-process.monitor
# 完整停用：monitor、daily、worker均bootout；不会删除版本、数据和通知。
```

当前已加载的三个作业全部在用户gui登录域，plist保留在项目，未增加LaunchDaemon、sudo服务或修改隐私权限数据库。加载与实际退出码证据在docs/evidence。Documents权限是macOS对该Python路径的实际授权前提，之前已处理；新机器须正常授权，不能绕过。

仅SELECT和关闭外部读取降低误用风险，不构成对恶意同OS用户的沙箱；可信作者仍能直接改文件。禁止将连接凭据写入SQL或策略，真实源凭据应来自批准的secret store。输入路径和备份目的地是可信操作员参数，没有对网络暴露任意路径接口。


项目级启动/停用与恢复已经实际验证：

```bash
./scripts/services.sh status
./scripts/services.sh restart
./scripts/services.sh stop
./scripts/services.sh start
```

脚本只管理 local.data-process.worker/daily/monitor 三个gui作业；restart先验证配置，再停止并重新加载；重复start不会重复注册。停止不删除数据，重新启动会核对中断实例。机器重启后仍需执行start（当前没有写入用户Library或机器LaunchDaemons）。如需无人值守跨登录自动启动，必须在实际目标服务账号和运维规范下安装，不擅自扩大机器权限。
