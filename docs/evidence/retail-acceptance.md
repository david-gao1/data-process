# 公开真实零售数据验收

2026-10-15。结果：在现有data-process中完成真实公开历史数据两批接入、受控交付与独立核对；不等同企业生产数据库接入或实时CDC验收。

## 官方来源与真实文件

UCI Online Retail，Chen, D. (2015)，DOI 10.24432/C5BW33，CC BY 4.0。来源与候选比较见[ADR](../adr/002-public-retail-source.md)。实测原始下载23,715,478字节，ZIP SHA `f5385cbb54bbebf7196389109c6b0621faab0c304e3702548165e71c84aede8b`；内含xlsx SHA `43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d`。两者独立在本Mac核对一致，见[下载原始输出](retail-download.json)。不是官方发布的数字签名，源身份依赖官方HTTPS与受版本管理的固定hash。

全量原文件独立读取结果：541,909行；135,080缺CustomerID、1,454缺Description、9,288取消、10,624负数量、2,515零价格、2负价格。它说明官网“无缺失”概括不足以当质量保证。CustomerID/Description本产品不用，因此不因它们缺失丢弃交易；取消与负数量不等价，按契约组合判定。

## 实际命令与结果

```bash
./scripts/setup.sh
.venv/bin/python -m data_process.public_retail --home .data-process/retail fetch
.venv/bin/python scripts/retail_e2e.py
.venv/bin/python -m pytest -v
./scripts/dp --home .data-process/retail trend --end 2011-01-31
./scripts/dp --home .data-process/retail check
```

- [全量测试](pytest-public-all.txt)：**45 passed**，原38项保持，新增7项公开接入/业务case。
- [真实E2E完整输出](retail-e2e.json)、[执行阶段日志](retail-e2e.stderr)：44日期、231国家日聚合与独立原始XLSX Decimal pass完全一致。
- 第一个历史月2010-12：42,481选定行，273非正价格隔离（约0.64%），42,208有效行，20日。
- 第二个历史月2011-01：35,147选定行，140非正价格隔离（约0.40%），35,007有效行，24日。
- 两月的同批重放返回原run并保持audit不增；第二月保持第一月正式指针。
- 共44日source，45个成功run（含1次发布恢复故障演练），46条audit（44正式发布+恢复替换+历史回滚）；失败的事务没有留下审计或改变正式指针。
- 截至2011-01-31最近30日窗口从2011-01-02开始，124国家日聚合；6天没有source记录，显式返回missing_dates，不伪造0。
- 备份restore后check通过、查询一致、两个batch原始/规范化hash校验通过。

| 历史批次 | 正向开票GBP | 取消金额GBP | 筛选后净开票GBP | 销售行 / 取消行 |
|---|---:|---:|---:|---:|
| 2010-12 | 823,746.14 | 74,789.12 | 748,957.02 | 41,480 / 728 |
| 2011-01 | 691,364.56 | 131,364.30 | 560,000.26 | 34,306 / 701 |

以上是明确筛选口径后的开票行金额，不是会计收入、利润、全部账单金额或支付网关实际退款。

## 故障验收

测试用小型合成XLSX fixture覆盖：网络异常、截断/hash不符、超限实际字节流被终止、未登记来源、坏ZIP、缺列、超过异常率、分币HALF_UP、取消与符号不一致、非正/NaN价格、缺可选字段、批次manifest篡改、跨产品home拒绝、正式输出无个人字段；失败不建ready/run或不发布。

真实数据执行SQLite trigger注入audit失败，确认旧正式指针不变；移除故障后显式恢复，再回滚历史成功版本。真实数据每个国家日与不调用normalizer/calculator业务函数的另一遍原始文件Decimal聚合对账。原有取消、超时、SIGKILL、并发和本地告警回归全部保持。

## 未宣称完成

两个历史月来自同一个静态快照，第二批验证的是回放增量；没有真实CDC或连续外网采集。没有上传原始明细、发送外部消息、付费服务、远程推送或新网络定时任务。未验证本企业源库权限、当前业务时区与财务口径、规模SLA或异地恢复；公开文件不提供这些生产保证。

来源归属、数据字典和逐步操作见[零售运行手册](../09-retail-dictionary-runbook.md)。
