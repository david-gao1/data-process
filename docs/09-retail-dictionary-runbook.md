# 公开零售数据字典与操作手册

## 来源与署名

Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5BW33 。许可 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，[官方数据与字段页](https://archive.ics.uci.edu/dataset/352/online%2Bretail)。本产品裁剪字段、筛选异常、逐行舍入并聚合，与原始数据不同；保留署名与处理说明。原始数据仅本机私有目录保存，未经授权不上传。

## 原字段与处理

| 原字段 | 含义与处理 |
|---|---|
| InvoiceNo | 单据编号，C开头表示取消；仅用于行分类，不进入规范化或交付 |
| StockCode | 商品代码，当前指标不用；不据此盲目去重 |
| Description | 描述，缺失可接受；不进入规范化或交付 |
| Quantity | 有符号数量；正价正数量非C为销售，正价负数量C为取消，其余按契约隔离 |
| InvoiceDate | 原始无时区datetime，取原日历日期；不编造UTC时刻 |
| UnitPrice | GBP单价；非正值隔离；Decimal乘数量后每行HALF_UP到便士 |
| CustomerID | 原客户编号；缺失不影响本国家日指标，不进入规范化或交付 |
| Country | 源国家/地区标签，保留原标签（例如United Kingdom），不假装ISO编码 |

规范化CSV：business_date、country、line_type(sale/refund)、amount_pence(非负整数)、source_row(原XLSX从1开始的行号，header=1)。来源身份由raw ZIP hash + worksheet + source_row组成，不依赖订单号唯一性。所有原行保留位置追溯，不无依据去重。重复运行的幂等由批次/运行/正式指针保证。

正式Parquet：business_date、country、gross_sales_pence、refund_pence、net_sales_pence、sale_lines、refund_lines，均为国家日聚合。gross/refund/net以GBP便士为单位；正向金额包含源中的正价费用行，不能称纯商品收入、利润或清算现金流。退款指标是取消行金额而非网关退款确认。net可为负。查询额外包含run_id/release_id/source_id，不包含客户、单据、商品或source_row。

## 有界运行命令

从项目根目录，先安装。公开接入是显式有限命令，没有外网定时任务。

```bash
./scripts/setup.sh
./scripts/dp --home .data-process/retail init
.venv/bin/python -m data_process.public_retail --home .data-process/retail fetch
./scripts/dp --home .data-process/retail release --product retail_daily
.venv/bin/python -m data_process.public_retail --home .data-process/retail ingest --month 2010-12
# 将上两步真实返回值填入 RELEASE 和 BATCH（不是命令字面值）：
.venv/bin/python -m data_process.public_retail --home .data-process/retail stage --batch BATCH --release RELEASE
./scripts/dp --home .data-process/retail worker
# 另一终端，对每个run先查状态、日志，审核后发布：
./scripts/dp --home .data-process/retail wait RUN
./scripts/dp --home .data-process/retail publish RUN --expected NONE --actor operator --reason '公开来源、口径与质量已核对'
./scripts/dp --home .data-process/retail trend --end 2010-12-23
```

第二月改为 `ingest --month 2011-01`，再stage/审核，旧月份指针不会追加。重复stage相同batch/release返回相同run；当前已是目标run的publish幂等不增审计。变更reader代码/hash或原始版本会产生新批次身份，属于显式重处理，需要对当前指针CAS审批。

一次完成全量E2E（首次运行目录可以已有fetch缓存，但应无先前E2E完成/backup目录；脚本不覆盖备份）：

```bash
.venv/bin/python scripts/retail_e2e.py
.venv/bin/python -m pytest -v
```

该有限脚本执行两个月、同批重放、发布故障/恢复/回滚、独立原文件逐日国家核对、备份恢复，结束会停止它启动的worker。要完全重新演练，请传全新的home路径；网络下载最多一个32MiB限额文件，后续cache命中不再次下载。

当前已交付数据可直接查询，无需后台worker常驻：

```bash
./scripts/dp --home .data-process/retail trend --end 2011-01-31
./scripts/dp --home .data-process/retail check
.venv/bin/python -m data_process.public_retail --home .data-process/retail verify --batch a54349ab99837d42468d49e2f78dfa92b56b0fdc47745540cbb9423dfc0da331
.venv/bin/python -m data_process.public_retail --home .data-process/retail verify --batch e04f936980db5419991d9ae4628904a1360f783f0f598de91aef8aacbea8a294
.venv/bin/python -m data_process.public_retail --home .data-process/retail trace --source bbc755cf49aa45808720a463d0cfc2dc4e10c21c0d916c5e18f8100c72bad002
```

这些batch ID绑定本次reader SHA，更新实现后应使用新命令返回值；旧版本和manifest继续可验证。

## 存储与恢复

- sources/uci-online-retail.json：Git内固定官方URL、许可、ZIP及XLSX SHA256、大小上限。
- home/raw/<ZIP-SHA>.zip 与.json：本机原始版本和下载来源元数据；缓存坏文件拒绝，不静默重下替换。
- home/ingestions/<batch-id>.json：月份、原始hash、reader文件hash/openpyxl版本、完整性摘要、质量计数、隔离源行号和日source映射。manifest有自身内容摘要。
- home/ingestions/normalized/：去除个人编号后的临时规范化日分区；home/sources/下是平台内容寻址快照。
- home/releases、candidates、control.sqlite：完全复用既有不可变版本、运行、发布与审计。

下载错误/超限/哈希不符只留下明确失败，不登记ready；临时目录退出清理。源结构错误、日期不可归属或选定月异常率>5%不登记任何日source。规范化批次写入若中断，尚未完成manifest的source不会被该批次stage；使用相同代码和raw重跑可按内容hash恢复。误发布以既有rollback按expected当前版本回退；不要修改源文件、成功状态或摘要。

备份必须保留整个home（含raw、ingestions和reader血缘），不只Parquet；本次真实数据恢复副本位于`.data-process/retail-backup`，已做check、正式查询和batch验证。该副本仍是本机备份，不是异地灾备。原始行和客户编号不会进入Git，只提交聚合验收证据。

资源边界：原始zip32MiB，workbook成员32MiB，xlsx内部声明解压总量384MiB，源行不超过600000；只读stream扫描工作表并在内存保存所选月规范化行，适合当前快照，不承诺任意规模out-of-core。运行计算子进程DuckDB memory_limit=256MB、threads=1，超时/取消沿用现有worker。

## 局限

这是公开真实历史数据的业务闭环，两个自然月来自同一个2010–2011快照，明确为历史批次回放，不是两次新发布源文件，更不是实时CDC。没有企业数据库连接、生产源权限、删除传播或持续更新。本次没有给现有launchd增加网络任务；原三省合成作业仍按已批准的到期策略运行。
