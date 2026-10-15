# 公开真实零售数据业务契约

2026-10-15；开发前确定。沿用现有平台，增加retail_daily产品，运行在独立home `.data-process/retail`。不更改现有合成演示作业，不新增自动外网下载。

## 业务与真实数据边界

目标：从有许可的真实历史交易明细，形成可追溯的每日各国家销售、取消退款和净额，供业务按最近30天查询。来源UCI Online Retail，Chen, D. (2015), DOI 10.24432/C5BW33，CC BY 4.0。原始业务时间2010-12-01至2011-12-09；它是静态历史快照，不是本企业生产数据库，也不是实时CDC。

第一次网络范围只允许UCI官方注册URL的一个zip，最多32MiB、连接15秒/传输120秒、无自动重试、无重定向、TLS验证保留；服务未给Content-Length时仍按实际流量限制。下载成功按SHA256固化原始文件和元数据，后续运行使用固定hash校验，不静默替换。zip中只读取指定xlsx成员，限制成员大小与xlsx内部解压总量，禁止extractall。

历史增量批次为自然月2010-12、2011-01，从同一真实快照重放；第二批只增加其日期分区，已有日期不追加。重复批次复用manifest和source，提交key不变，正式指针不重复发布。原文件修订须新hash、新manifest和显式重处理；不是删除/更新CDC。

## 输入与处理口径

原始xlsx表头严格为InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country。以只读流式解析保留原文件；使用订单原始无时区日历日期，不把它误解释成UTC时刻。missing CustomerID和Description不影响本产品，因为不参与聚合；这不意味着原数据无缺失。源级列缺失/坏文件整批拒绝。

- 正常销售：数量>0、单价>0、订单不以C开头。
- 取消退款：数量<0、单价>0、订单以C开头；作为负向金额归属该取消行日期，不追溯改写原销售日。它表示源数据中的取消交易金额，不宣称是支付网关实际退款确认。
- 零/负单价、零数量、负数量但非C订单、C订单正数量、缺国家/订单/无效日期或数值进入隔离统计；按原因计数与源行序号摘要，不在交付中输出原始记录。异常率>5%拒绝所选批次。
- 金额=quantity×unit_price（GBP），用Decimal计算，每行按HALF_UP舍入到整数便士；退款以绝对值保存。记录发生分币舍入的行数，避免浮点汇总。
- 不自动删除相同明细：源未提供可靠唯一行主键，重复订单商品行可能有业务含义；批次幂等不等于替源纠正重复交易。

规范化日CSV只保留business_date,country,line_type,amount_pence,source_row；去除CustomerID、InvoiceNo、StockCode、Description。原始文件和隔离行号仅本机0700目录保留，禁止对外上传。

## 输出契约

净额是按本契约筛选后的净开票金额，不是会计收入、利润或全部现金流。每(date,country)唯一，字段business_date VARCHAR、country VARCHAR、gross_sales_pence BIGINT、refund_pence BIGINT、net_sales_pence BIGINT、sale_lines BIGINT、refund_lines BIGINT。gross/refund非负，net=gross-refund，行数加总等于规范化可用明细数。没有业务的日期不伪造0，查询继续列missing_dates。每个run输出与独立Python整数聚合完全对账，并与原始行Decimal汇总/批次manifest对账。

交付仅国家日聚合及release/source/run血缘。复用既有异步worker、取消/超时/恢复、候选隔离、CAS发布、审计、回滚与备份。核心改动限定注册固定产品计算器和通用结果列读取，不新增调度器或第二套发布事务；一个home只允许一种产品，避免日期指针冲突。

## 验收

| ID | 必须验证 |
|---|---|
| P01 | 官方TLS下载、字节上限、原始hash/来源/许可/reader版本追溯；固定hash缓存重用 |
| P02 | 下载失败/截断/超限/坏zip或xlsx/缺列/来源URL不符/hash不符不能标为ready或发布 |
| P03 | 异常行按明确原因隔离，超阈值批次失败；便士舍入、退款和缺CustomerID可独立核对 |
| P04 | 第一月真实数据→日source→异步run→质量→受控发布→业务查询完整执行 |
| P05 | 同月重放run和交付不重复，第二历史月增加分区且旧月指针保持；明确是历史回放 |
| P06 | 发布注入失败保留旧交付，移除故障后显式恢复，历史回滚可读；原始hash与批次归属均可核对 |
| P07 | 原38项回归保持；现有launchd合成作业不改成外网任务；正式查询无个人编号与原始记录 |

不是实时业务平台生产接入验收：不验证实时CDC、源数据库权限、删除传播、支付退款状态或当前经营SLA。
