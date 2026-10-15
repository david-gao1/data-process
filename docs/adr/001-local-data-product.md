# ADR-001：单机可验证数据产品

日期：2026-10-15；接受；适用首条三省活跃统计闭环。

## 矛盾

统一可追溯交付和故障恢复是当前风险；机器没有运行 Docker，真实源凭据未提供。完整湖仓与编排栈的部署成本不能替代正确性证明。

| 方案 | 复用价值 | 本期代价 / 决定 |
|---|---|---|
| Prefect + DuckDB | 运行、部署、取消、重试、可观测 | server/worker/deployment 增加运行面；单流程不引入，下一阶段优先评估 |
| Dagster + DuckDB | asset/partition/checks 与数据平台匹配 | daemon/webserver/metadata/config 增加学习及部署面；多资产依赖出现时评估 |
| Spark + Iceberg + catalog | 多引擎共享表和快照提交 | 首条小规模本机任务不需要分布式算力；延后 |
| Python/OS + DuckDB/Parquet + SQLite | SQL/Parquet/事务/进程终止均复用成熟底座 | 接受少量队列、单机生命周期及发布业务代码，必须做故障注入 |

选最后一项。没有已接入的编排器，因此本机队列没有重复工具的调度/重试责任；完全不自研日历调度或自动重试。未来采用编排器时移除本地 worker，保留输入/版本/发布契约。没有为 AI 增加向量库、Agent、消息队列；Parquet 和版本血缘可供未来特征/训练数据使用。

## 来源与阅读结论（官方，访问 2026-10-15）

- [DuckDB Parquet](https://duckdb.org/docs/current/data/parquet/overview)：原生 SQL 读写 Parquet，适合本地分析。
- [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency)：不能把嵌入式数据库默认当多进程共享写库；本版计算使用独立内存连接，只共享不可变 Parquet。
- [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html)：复用事务保证 delivery/audit 同时提交；硬件 flush、文件系统假设仍存在。
- [Prefect cancellation](https://docs.prefect.io/v3/advanced/cancel-workflows)：取消需要 deployment 和监控进程；不把装饰器当可靠取消的证明。
- [Dagster assets](https://dagster.io/docs/guides/build/assets)：定义、物化和资产检查可作为后续演进的责任映射。
- [Iceberg spec](https://iceberg.apache.org/spec/)：提供表元数据、快照和提交模型；Parquet 本身不等于湖仓表事务。
- [Python 3.10 subprocess](https://docs.python.org/3.10/library/subprocess.html)：复用 Popen/terminate/kill/wait；限定本地子进程，不外推分布式取消能力。

只读本地方法论目录 `/Users/lianggao/MyWorkSpace/999个人知识库/0001-软件工程/003架构/000架构出发点与方法论` 全部 Markdown 与 HTML 已阅读。采纳“目标→职责→模型→机制→取舍→验证”，重点深入正确性和可恢复性，记录薄 System Map 与当前关键风险，不把技术目录当目标。

只读参考 [mini-llm](https://github.com/david-gao1/mini-llm/tree/e697ab5c8799b6c5716a30a43fa243236add4f04) 的 README、HARNESS、SPEC、testing：借鉴每项需求具备边界契约、执行命令和通过判据，使用 uv 锁依赖与分层验收。未修改用户参考项目；只在 /tmp 放阅读副本。

## 失效和演进触发

单机停机可接受但不能丢失正式版本；暂停期间无 SLA 保证。需求出现定时/DAG/自动重试时接入现成编排，出现真实多用户时增加独立账号/API授权，出现多机共享写时选择 Iceberg catalog 与对象存储。以实际运行容量和故障证据触发，不能按“以后可能 AI”堆组件。

## 补充：无 Spark 的真实 Iceberg 路线

比较 `PyIceberg + PyArrow 写入 + DuckDB SQL + 本地文件/SQLite catalog`：比纯 Parquet 多了表级 metadata/snapshot 与 catalog 提交，可在本机成立，无需 Spark。其收益是标准表格式与历史 snapshot 读取；代价是本版只有每日三行产品仍需额外维护表元数据、snapshot 保留与 catalog 迁移。[PyIceberg configuration](https://py.iceberg.apache.org/configuration/) 的 SQLite 路径面向本地开发，不能当生产 catalog 承诺。现阶段不采纳，不把这个候选描述成“必须上 Spark”。

[DuckDB Iceberg 扩展当前资料](https://duckdb.org/docs/current/core_extensions/iceberg/overview) 包含 catalog 读写能力；本版固定 DuckDB 1.4.1，仅验证原生 Parquet，不安装 Iceberg 扩展，未验证任一 REST catalog 读写子集。不能从本版选择推出 DuckDB 永远只能读 Iceberg。迁移时需要固定 DuckDB/扩展/PyIceberg 版本并重新做兼容性验收。

[Iceberg reliability](https://iceberg.apache.org/docs/latest/reliability/) 的快照属于单表提交，不是整个流水线事务。将来多表正式交付 manifest 应固定各表 snapshot ID，由一次业务发布决定消费集合。snapshot 也不是备份，仍需 [maintenance](https://iceberg.apache.org/docs/latest/maintenance/) 与异地恢复。PyIceberg to_duckdb 内存转换不能自动视为大数据 out-of-core 路径。

## 实验后的决定

实际完成 [PoC](../../experiments/iceberg/poc.py)，固定 PyIceberg 0.10.0 / PyArrow 26.0.0 / DuckDB 1.4.1。见 [运行结果](../evidence/iceberg-poc.json)：两次写入 snapshot 不同，旧快照计数 3、新快照计数 4，catalog 重开可读取，Arrow 桥接 SQL 查询旧值通过；因此本地无 Docker 的 Iceberg 路线确实可行。首次重开使用不同 catalog 名导致找不到表，改成原 catalog 名后通过，体现迁移时不能忽略 catalog 身份。

最终仍选 Parquet 产品交付：当前只有一个日期分区、三行结果、整分区替换且没有跨引擎表写入；内容寻址 release/source 与逐 run 留存已覆盖本期历史读取和回滚，SQLite 指针是业务发布职责，即使采用 Iceberg 也不能省略。主环境实际 7 个安装包，实验环境 30 个；差异是可测的安装面而非 Docker 约束。接受暂不具备标准 Iceberg 表快照、schema evolution 和跨引擎 catalog 的局限。若业务要求任一标准表能力，优先把当前候选存储替换为已验证 PyIceberg 路线，正式 manifest 存 snapshot ID；不复刻 Iceberg。当前 SQL/独立 oracle 会将一天输入载入 Python sets，明确只适合首个小数据产品，不能宣称无限量 out-of-core。

新增每日交付采用 macOS 原生 launchd：worker KeepAlive 与每日触发分工；daily 只执行一次预先批准的 release 策略，无日历计算队列、无自动重试。自动发布必须显式 `auto_publish=true`、固定 release、输入 ready 摘要与质量门禁；管理员人工发布若已替代该 run，旧定时触发不覆盖。用户登录域的 launchd 作业不等于无人登录生产服务。
