# 实施日志

## 2026-10-15

1. 检查工作目录、项目指令、git、Python、uv、Docker。目标为空仓库，本地无副本；在授权网络读取下克隆到当前工作目录。Docker daemon 未运行。未覆盖任何用户变更。
2. 开发前只读方法论全部 Markdown/HTML；只读克隆 mini-llm 到 /tmp，固定参考 commit，阅读契约与 Harness。网上读取官方 DuckDB/SQLite/Prefect/Dagster/Iceberg/PyIceberg/Python 资料。
3. 先写业务契约、系统职责与 ADR，再实现。选择本地 Parquet 数据产品和 SQLite 发布指针，保留标准表格式演进边界；不为了未来 AI 加额外服务。
4. 实现 ready 快照、SQL/代码/锁文件 release、异步 run、OS 子进程、质量 oracle、候选隔离、CAS 发布、审计、回滚、取消/超时、父进程丢失防护、重启对账、备份/恢复检查。
5. 初次安装可编辑包后导入失败。查 Python verbose 和 site.py，发现 `.pth` 被系统标记 UF_HIDDEN，Python 跳过；重建文件短暂恢复，随后再次隐藏。改成 uv 普通安装，固定 scripts/dp 项目入口，最终安装源码摘要逐文件核对一致。失败未归咎于业务测试，保留此处修复原因。
6. 独立 PyIceberg PoC：初次用不同 catalog 名重开导致 NoSuchTable，使用原 catalog 名后历史快照/覆盖/持久读取/Arrow桥接通过。实测主环境7包，实验环境30包。最终保留纯 Parquet，并明确它没有标准 Iceberg 表级快照，不能用 Docker 未启作为理由。
7. 补充每日闭环：复用 macOS launchd 的日历与 worker KeepAlive，daily 使用 pinned release + ready checksum + 自动发布策略。测试覆盖重放幂等和人工取代后拒绝旧策略覆盖。
8. 16 项测试全部通过；真实 CLI 连续生产并发布 30 天，正式查询90行且无缺失日期。执行了真实子进程 SIGKILL、取消、超时、单worker竞争、发布竞争与本机备份恢复。
9. launchctl 在受限环境 bootstrap 返回错误5；在授权的本机上下文中加载成功。进程仍无日志，用 sample 发现 Python 启动时 open 阻塞，tccd 日志确认 DocumentsFolder 权限提示。没有修改权限数据库或绕过系统安全。用户处理权限后运行恢复，daily 计算并发布成功，退出码0。
10. Finder 只读界面诊断曾因环境断开超时，未返回可确认结果；不重复未知 UI 操作。用户已明确允许使用 Finder，后续状态通过终端只读结果确认即可，无需再操作 Finder。
11. 正式数据、环境、测试、Iceberg、launchd 证据保存在 docs/evidence。实现与文档保持本地 Git 管理；未 push、未建 PR、未公开部署、未更改参考项目和知识库。

## 接受的边界

数据和业务口径全部合成假设；用户登录域不是无人值守生产服务。周期实际注册并用 kickstart 运行相同命令验证，未等待次日日历触发。没有真实 MySQL/Hive/StarRocks、真实权限或源完整性验收。生产缺口与解决路径见运行手册；不能用本机绿灯代替生产验收。
