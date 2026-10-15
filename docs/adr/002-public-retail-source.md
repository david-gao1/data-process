# ADR-002：首个公开真实业务数据源

2026-10-15；开发前接受UCI Online Retail。目标是验证真实输入质量、批次接入和平台交付，不需要凭据或付费服务。

| 候选 | 官方来源与许可 | 规模/稳定性/更新语义 | 取舍 |
|---|---|---|---|
| Northwind | Microsoft sql-server-samples/northwind-pubs；仓库MIT | 实测instnwnd.sql 1,049,720字节；静态示例SQL，适合关系连接和join | 不是实际业务生产数据，不满足本轮真实数据证据 |
| NYC TLC Green | TLC官方月度Parquet与zone lookup；NYC FAQ说明开放数据可不受限制使用，结合网站使用条款；不能擅自标CC BY | 2025-01实测1,178,451字节，月度发布通常延后两月；源声明不保证准确性，schema随年份变动 | 更小、天然月度批次，后续持续文件接入优先候选；本轮不额外下载 |
| UCI Online Retail | Daqing Chen，DOI 10.24432/C5BW33，官网CC BY 4.0 | 541,909行，xlsx官网22.6MB；固定2010–2011真实零售交易快照，无账号；HEAD 200未给长度，需实际流量上限 | 许可清楚、包含取消和质量问题，选择；增量必须标为历史回放 |

来源（访问2026-10-15）：

- [UCI数据页](https://archive.ics.uci.edu/dataset/352/online%2Bretail)，原始链接由该页给出；[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。署名：Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5BW33。
- [TLC官方数据页](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)、[NYC FAQ](https://www.nyc.gov/opendata/get-started/FAQs)、[使用条款](https://data.cityofnewyork.us/stories/s/Terms-of-Use/k9k7-3cje)。稳定URL也可能发生修订，需内容hash，不能把ETag当通用SHA。
- [Northwind官方仓库](https://github.com/microsoft/sql-server-samples/tree/master/samples/databases/northwind-pubs)、[MIT许可](https://github.com/microsoft/sql-server-samples/blob/master/license.txt)。不下载或执行Northwind SQL，仅核对HEAD与说明。

网络探测发现本机Python默认CA信任失败，系统curl保持TLS校验能读取官方URL。选择curl作为有界HTTPS传输底座，流式读取并计数，禁用重定向、设置超时，不使用不安全的-k或关闭校验。下载临时文件校验后才进入内容寻址raw目录。固定源URL和hash，不能用CLI变成任意URL下载器。

复用现有平台：只新增登记的retail计算器与日聚合SQL，release保存选定计算代码；worker/发布/恢复逻辑不因数据源改变。正式查询改为按实际Parquet列返回字典，保留默认活跃产品输出兼容。不同产品使用独立home，注册版本时阻止混用。原始zip/版本manifest、只读解析与规范化是接入职责，核心不感知Excel或网络。

不用Iceberg解决本轮新矛盾：两月历史回放仍是整日不可变替换，不需要跨引擎共享写。公开数据的来源校验、隐私裁剪和退款口径不能由表格式代替。已有真实Iceberg PoC继续有效。

只读XLSX采用openpyxl流式reader，作为生产接入代码的可重复依赖；不制作或修改工作簿。数量和金额由Decimal/整数处理，正式交付不含CustomerID。只承诺按契约解释历史取消，不将其称为财务已清算退款。
