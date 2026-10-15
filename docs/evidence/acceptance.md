# 本机验收报告

日期：2026-10-15。结果：最小本地业务闭环和限定范围的运行保障通过；真实生产上线尚未验收。

## 环境与可复核证据

- macOS 27.0.1 arm64；Python 3.11.8；DuckDB 1.4.1；pytest 8.4.2。完整环境与“安装代码等于源代码”摘要核对见 [environment.json](environment.json)。依赖 uv.lock 固定，普通安装。
- 目标目录 `/Users/lianggao/Documents/Codex/2026-10-15/task/data-process`，新空仓库本地实现；网络读取参考不修改它。Docker 未运行且本版无需 Docker。
- 全部业务数据为 synthetic；三省演示口径：北京3、上海4、广东5，重复事件已去重。

## 实际命令与结果

| 命令/实验 | 结果与证据 |
|---|---|
| `./scripts/setup.sh` | 独立 .venv 普通安装通过；修复 Mac hidden .pth 问题 |
| `.venv/bin/python -m pytest -v` | **16 passed**，见 [pytest.txt](pytest.txt)。覆盖正常交付/错输入/错误SQL/幂等/版本/发布竞争/取消/超时/SIGKILL恢复/单worker/篡改/备份恢复/窗口/每日策略 |
| `.venv/bin/python scripts/demo.py` | **连续30天、90行、30个成功run、0缺失日期、integrity ok**，见 [demo.json](demo.json)。通过真实 CLI 提交、后台worker、审核发布和正式消费 |
| `experiments/iceberg/.venv/bin/python experiments/iceberg/poc.py` | 真实两个 snapshot、旧值3/新值4、catalog 重开与 DuckDB Arrow查询通过，见 [iceberg-poc.json](iceberg-poc.json) |
| `plutil -lint .data-process/launchd/*.plist` | 两份 plist 均 OK |
| `launchctl bootstrap gui/501 …worker.plist` 与 `…daily.plist` | 用户登录域加载成功；worker KeepAlive，daily calendarinterval 08:00（系统本地时间 CST） |
| `launchctl kickstart gui/501/local.data-process.daily` | 实际触发：run `8742da569c3d452f97f9a6cdde7fc80e` 计算成功并按 pinned release 自动发布，退出0；重放验证见 [daily-execution.json](daily-execution.json) |
| `scripts/dp --home .data-process/live trend --end 2026-10-14` | 正式查询3行、缺失29天明确列出；见 [daily-trend.json](daily-trend.json) |
| `scripts/dp --home .data-process/live check` | integrity ok，见 [live-check.json](live-check.json) |
| 测试内 `backup → copytree → check → trend → rollback` | 还原副本完整性通过，历史回滚不影响原目录 |

launchd 实时状态见 [worker](launchd-worker.txt)、[daily](launchd-daily.txt)。初次启动曾被 macOS DocumentsFolder 权限提示阻塞，在权限处理后通过；配置文件存在本身未被当作成功证据。

## 已验证的故障语义

- 错误日期、空用户、未知省份、缺省、schema错误、COUNT(*)错误SQL、输入与版本篡改，均无法形成有效交付。
- 候选质量通过不自动暴露，发布必须人工审核或显式预批固定版本策略。
- 同日期重跑只有一个正式指针；并发审批一成功一冲突；key重放返回同一run，改参数冲突。
- 真实运行中取消/超时均终止并wait本地子进程，不能发布；worker SIGKILL 后旧run变 INTERRUPTED，排队run可继续；无自动重试。
- 历史成功版本回滚，前后run/actor/reason写audit；正式产物损坏时查询拒绝。
- 每日 ready 缺失/错误阻止运行，策略重放不重复发布，旧自动任务不覆盖人工替换。

## 未覆盖与生产缺口

未连接真实数据库，未验证 MySQL/Hive/StarRocks 抽取、源水位、迟到修订或业务签字口径；未验高容量、多租户、远程取消、分布式一致性、NFS、真实断电与异地灾难恢复。未验证原生 DuckDB Iceberg REST扩展（实验使用Arrow内存桥接），未采用生产Iceberg catalog。

launchd 的实际日历事件已注册，但没有等待次日08:00；用 kickstart 执行同一命令验证，不虚称已跨日运行。当前登录域重启/退出登录需重新 bootstrap，未来日期没有真实上游 ready 会明确失败。无UI，因此不存在未执行的网页E2E；没有公开网络入口。

本机底线已完成：可重复部署、运行、失败关闭、版本追溯、受控交付和恢复。真实生产必须沿 [运行手册](../04-runbook.md) 完成服务账号、源连接、权限与凭据、数据口径/时区、容量/SLA、告警、备份异地恢复和目标环境演练后才能签署上线。

## 最终质量审查更新

最初16项通过后继续审查，最新总闸门为 [38 passed](pytest-review.txt)，原始16项证据保留为历史。最终代码重复完成 [30天CLI闭环](demo-review.json)。新增缺输入/逾期/失活的 [本地通知演练](operations-proof.json)、[实际health](health-live.json)、用户gui域小时monitor，以及发布/audit故障事务、并发daily、取消/中断迟到完成门禁、凭据/SQL/路径边界的独立验证。完整发现和修复见 [质量审查](../07-quality-review.md)。生产接入缺口依然成立。
