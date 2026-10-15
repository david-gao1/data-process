# 独立质量审查与补强结果

日期2026-10-15。本轮是重新从故障和安全边界审视已有代码与测试，不是第二位人工审计，也不构成真实生产验收。

## 对原16项验收的判断

原16项是pytest收集的case数，包含5组错误输入参数，并非16个独立业务场景。fixture为每项建立新home，使用真实SQLite、DuckDB、Parquet与OS进程；正常统计使用硬编码3/4/5期望，独立于SQL输出；发布竞争用多线程独立连接，不是仅断言函数自身返回值。

发现原用例证据不足：取消在RUNNING状态就触发，SIGKILL只等run.log存在，两者都可能发生于真正启动计算前。已收紧：必须看到子进程已完成输入检查的日志，再取消或杀父进程；SIGKILL后恢复必须在5秒内完成，明显早于注入的10秒计算延迟，验证父进程guard和继承锁释放路径。备份原用例验证成功版本，现补充排队/取消状态还原。

## 发现、修复与证据

| 问题 | 修复 | 独立判据 |
|---|---|---|
| 完成状态写入没有统一阻止迟到回调 | finish_run只允许RUNNING/CANCELLING完成，已终态不复活；非成功清空产物指纹 | 已有真实结果文件，模拟完成提交前取消，迟到成功仍CANCELLED且不可发布；INTERRUPTED同样拒绝 |
| 同时daily触发同一个run，第二个可能因过期baseline报失败 | 当前已是目标run则幂等返回，正式替换仍CAS，已被人工取代则拒绝 | 两线程真实daily+后台worker，单个daily run和单条audit，无虚假daily失败 |
| 发布事务仅测正常和竞争 | 注入BEFORE INSERT audit失败 | delivery和audit一起回滚，旧查询保持，显式再次发布后成功 |
| 磁盘manifest未核对 | verify_release同时核对registry和manifest.json | 篡改manifest后发布被拒绝 |
| SQL定义允许多语句或副作用语句 | DuckDB解析后仅接受一个SELECT；加载源后关闭external access | 多语句/COPY/INSTALL/CREATE拒绝；read_text秘密哨兵文件失败且日志不含哨兵 |
| URI路径带?/#会影响SQLite连接 | 使用Path.as_uri转义 | 所有新增fixture使用含?/#的home并完成真实运行、备份、查询 |
| 凭据继承边界缺少测试 | 子进程仅传PATH/PYTHONUNBUFFERED | 注入AWS/MySQL测试哨兵并捕获真实Popen环境，只允许两个键 |
| 缺输入只有日志，worker无健康状态 | 严格配置、心跳、交付截止、状态码、local outbox | 缺ready不建run/不发布，健康显示input_not_ready/overdue，通知去重 |
| 通知落盘失败会丢失或重复 | SQLite事务outbox+不可变JSON文件，串行投递 | 注入磁盘写失败pending=1，恢复后落盘并pending=0，重复调用仍一个文件 |
| 演示未来每天缺输入 | through_date、enabled，daily不KeepAlive重试 | 到期返回disabled_or_expired，不建run、不发缺输入告警；完整停用脚本保留数据 |
| launchd异步bootout后的旧注册被start误判 | stop等待旧注册消失，start确认新心跳 | 连续两次实际restart通过，见service-restart原始证据 |
| worker停止心跳可能覆盖新worker心跳 | owner检查后更新stopped | 旧owner停止不能覆盖新owner活跃状态 |

测试中的终态边界通过受控数据库状态布置确定性模拟提交时序，OS取消/SIGKILL另有真实进程验证；不宣称已穷举任意时间竞态。SELECT限制也不是对恶意OS管理员的沙箱。

## 原始命令和结果

```bash
./scripts/setup.sh
.venv/bin/python -m pytest -v
.venv/bin/python scripts/demo.py .data-process/review-demo
.venv/bin/python scripts/verify_operations.py
./scripts/services.sh restart
launchctl kickstart gui/$(id -u)/local.data-process.daily
launchctl kickstart gui/$(id -u)/local.data-process.monitor
./scripts/dp --home .data-process/live health --config .data-process/live/daily-policy.json
```

- [pytest-review.txt](evidence/pytest-review.txt)：**38 passed**，包含原验收与新增故障/配置参数组。
- [demo-review.json](evidence/demo-review.json)：最终代码再次完成连续30天90行、30成功run，完整性通过。
- [operations-proof.json](evidence/operations-proof.json)：显式合成时钟，2次缺ready+2次monitor，恰好3份本地通知，无run、无发布、无外部发送。
- [health-live.json](evidence/health-live.json)：实际运行worker心跳活跃、正式昨日已交付、待投递0。
- [launchd-monitor.txt](evidence/launchd-monitor.txt)：用户gui登录域、3600秒间隔、手动触发相同命令退出0；worker/daily状态见同目录review证据。
- [service-restart.txt](evidence/service-restart.txt)：对运行中的服务实际restart，旧注册消失后新worker处于running；随后daily/monitor均退出0、health正常。
- 服务作业基于原本地周期交付授权以及继续补齐生产保障的明确要求，在用户gui域加载；没有增加机器级LaunchDaemon、修改TCC数据库、安装Library持久启动项或发送消息。

## 核心模型、数据流与文件清单

Definition(SQL) → Release(SQL/compute/lock/runtime hash) → Source(日期+内容hash的ready快照) → Run(异步实例) → Candidate(Parquet+quality) → Delivery(日期唯一正式指针) + Audit；health和notifications贯穿运行。

核心文件：core.py（registry/状态/事务发布/备份）、compute.py（固定SQL与独立oracle）、worker.py（进程与恢复）、daily.py（预批策略）、operations.py（配置/健康/outbox）、cli.py（入口）；definitions固定口径；scripts管理部署/演示/launchd/演练；tests两份独立验收文件；docs记录契约、ADR、来源、追溯、原始证据和恢复。

## 剩余缺口

本轮无需真实凭据即可完成的状态门禁、竞态、配置、健康、周期失败控制、通知落点和恢复操作均已补齐。仍需要真实信息的是源连接/水位、业务时区与口径、目标机器和服务身份、数据规模/SLA、告警目的地与授权、RPO/RTO和异地存储。最小问题清单及接入判据见 [生产接入](06-production-handoff.md)。本地通知不等于已触达值班人员，用户登录域不等于无人登录生产部署。
