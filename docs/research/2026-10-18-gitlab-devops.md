# GitLab DevOps 调研：data-process 的交付闭环与可视化边界

调研日期：2026-10-18。资料仅使用 GitLab 官方文档及 DORA 官方研究；全部链接于本日访问。GitLab 在线文档持续更新，可能包含高于本地 19.4.2 的功能；本报告不将在线页面视作本地实例的验收证据，具体菜单、版本及许可仍须在实施时核对。

## 结论与适用前提

**研究结论：现有 GitLab CE 可以作为需求、代码评审、CI、软件制品与发布记录的管理入口，但现有 Runner 的权限边界不支持直接接管 macOS 业务运行环境。前端可视化应展示可信状态与证据，不能靠增加一个仪表盘就宣称已经完成 CD。** GitLab 的环境页面管理部署目标与部署记录，不等于自动具备目标机操作能力。[GitLab Environments](https://docs.gitlab.com/ci/environments/)

本项目上下文由本次任务提供：本地 GitLab CE 19.4.2、官方 Runner 19.4、专用容器内 shell executor，仅允许 protected main；无 Docker socket、sudo、特权模式及宿主机业务目录挂载。业务为 Python wheel，按精确 Git SHA 交付；SQLite 与不可变 Parquet 保存业务状态，macOS launchd 运行，目前没有管理 UI/API。这些是方案约束，并非本次联网调研重新验收的部署事实。

**实施建议：以用户已选择的“业务与研发交付统一门户，先只读概览”为首个功能，逐步建立“工作项 → MR → main CI → wheel/清单 → 隔离环境人工安装 → 运行反馈”的最小闭环。** CI 只接触代码、合成测试数据与允许发布的制品；真实业务数据留在业务运行侧。代码版本与数据批次必须分开追踪，不能将一次 Parquet 生成算成一次软件部署。

## 免费能力及付费边界

下表是官方当前文档的许可口径，表示能力可用范围，不表示本地已经启用。不要把 Free 的全部能力自动等同于 CE 每项实现；CE 实例以实际界面和版本验证为准。

| 环节 | CE/Free 可采用的基础方式 | 不应假设免费具备的能力 |
| --- | --- | --- |
| 计划 | Issues、标签、项目 Issue Board；用标签列表表达待办、进行中、待验收 | 配置范围看板、负责人/里程碑/状态列表、WIP 限制等高级功能为 Premium/Ultimate；Free 支持多个项目看板、一个组看板。[Issue boards](https://docs.gitlab.com/user/project/issue_board/) |
| 评审 | MR、讨论、评审人及可选 approval；结合受保护分支控制谁可合并 | Free approval 不阻止无审批合并；强制 approval rules、Code Owners 等需 Premium/Ultimate。[Approvals](https://docs.gitlab.com/user/project/merge_requests/approvals/) |
| 集成与制品 | CI job、job artifacts；Python 包可选 GitLab PyPI Registry | 制品保存期限、备份及容量需要实际治理，不能假定 artifact 永久保存。[Artifacts](https://docs.gitlab.com/ci/jobs/job_artifacts/)、[PyPI Registry](https://docs.gitlab.com/user/packages/pypi_repository/) |
| 发布与环境 | Releases、基础 Environments/Deployments 记录 | Protected environments、部署审批需 Premium/Ultimate；一个 manual job 不等于独立的审批制度。[Releases](https://docs.gitlab.com/user/project/releases/)、[Protected environments](https://docs.gitlab.com/ci/environments/protected_environments/) |
| 安全与度量 | 普通 CI 可运行自选检查并保存报告；可自己采集交付事件 | GitLab Security dashboards 和原生 DORA analytics 均为 Ultimate，不能在 CE 上承诺同名原生功能。[Security dashboards](https://docs.gitlab.com/user/application_security/security_dashboard/)、[DORA metrics](https://docs.gitlab.com/user/analytics/dora_metrics/) |

Release 页面本身免费，但 release evidence 各子功能存在额外限制：文档将主动收集列为 Self-Managed Premium/Ultimate，将 report artifacts 纳入证据列为 Ultimate。因此项目应保存自己的版本清单、校验和与验证摘要，不依赖付费 evidence 自动收集来满足可追溯要求。[Release evidence](https://docs.gitlab.com/user/project/releases/release_evidence/)

## 从需求到反馈：最小闭环如何运转

**计划与评审。** 每个 Issue 说明业务问题、验收条件、风险与回退方式，关联 MR 和最终 Release；通过标签看板看阻塞，而不是复制业务任务状态。MR 保留变更解释和验证证据。受保护分支流程允许开发分支提交、由具备权限的人合并；但 Free 的评审约定不能描述成平台强制多人审批。[Protected branch flow](https://docs.gitlab.com/user/project/merge_requests/authorization_for_merge_requests/)、[Approvals](https://docs.gitlab.com/user/project/merge_requests/approvals/)

**当前 CI 的真实能力。** Protected Runner 用于受保护引用；MR 使用受保护资源还要求源、目标分支均受保护、同一项目、触发人有目标分支权限及相应设置。普通未保护 feature 分支发往 main 的 MR 因而不能指望当前 Runner 执行，单加 `merge_request_event` 规则不能越过这些条件。[Runner protection](https://docs.gitlab.com/ci/runners/configure_runners/)、[MR pipelines](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/)

**实施建议：保持 main-only 边界，诚实展示“合并前本地验证、合并后可信 CI”。** MR 附本地检查证据，main CI 执行自动测试、wheel 构建、安装后 smoke test、输出清单；只有成功的精确 SHA 才可进入人工发布。它存在合并后才发现错误的窗口，需明确登记。将来若需要 MR CI，应另行设计无业务凭据、无部署能力、隔离且可清理的验证执行环境；不通过取消 Protected、扩大现有 Token 或保护全部开发分支来解决。

**制品与代码发布。** 推荐 release manifest 记录 Git SHA、wheel 文件名、SHA-256、依赖锁定摘要、Python/平台约束、pipeline/job 链接及测试结果。Linux shell 容器验证不替代 macOS launchd 目标机 smoke test。Release 链接精确制品并说明兼容性与回退版本；发布时使用已验证 wheel，不从移动分支重新构建。GitLab artifacts 支持路径白名单与有效期，正式版本可转入包仓库并配套保留策略。[Artifacts](https://docs.gitlab.com/ci/jobs/job_artifacts/)、[PyPI Registry](https://docs.gitlab.com/user/packages/pypi_repository/)、[Releases](https://docs.gitlab.com/user/project/releases/)

**部署与运行。** Shell executor 在 Runner 所在环境执行脚本，依赖同机安装，作业之间隔离有限，官方要求仅执行可信用户的构建。在本项目的专用容器里，“shell”指容器环境，不是 macOS 宿主机。无 socket、宿主机挂载及其他已授权控制通道时，不能由此执行宿主机 Docker 部署或修改 launchd。[Shell executor](https://docs.gitlab.com/runner/executors/shell/)

**实施建议：初期由运行侧人工下载指定制品、校验摘要、安装到版本目录、执行 smoke test，再按明确步骤切换 launchd，并记录实际结果。** 成功必须以目标环境完成健康检查为准，不能用构建成功代替。后续可单独评审 pull-based 的窄权限部署代理：目标机主动拉取允许版本，只接受固定动作与路径，限制凭据、保留审计和回退能力。它是未来设计方向，不是已部署组件；部署能力与凭据设计应走 Standard Lane。外部部署完成后可通过 Deployments API 登记环境记录，但应由可信执行结果驱动，不能在未部署时预填成功。[External deployment tracking](https://docs.gitlab.com/user/analytics/dora_metrics/#without-using-gitlab-cicd-pipelines)

## 代码交付与数据交付必须分账

以下为本项目的设计建议，不是 GitLab 内建业务模型。代码发布对象是 wheel、Git SHA、部署环境与运行版本；数据交付对象是业务批次、输入清单、处理参数、输出 manifest/摘要、质量检查及交付回执。两者通过软件 commit、`run_id`、现有 `source_id` 和业务日期关联，保持一份代码可处理多批数据、一批数据可重跑的事实。

前端先展示只读概览：运行版本、最近代码发布、main CI、当前批次、排队/运行/失败数、数据新鲜度和可追溯链接。GitLab 继续管理需求和代码交付，SQLite/Parquet 的业务事实由业务服务提供，不从 GitLab pipeline 状态推断。不要让浏览器直接读写 SQLite，也不要在浏览器放 GitLab Token；API、认证、授权、并发控制和数据变更须另行设计审批。UI 中样例数据必须标明“演示”，连接失败应显示未知/不可用，不能显示假成功。

数据回退不能等同于重装旧 wheel：SQLite 状态变化、业务去重和输出已交付等事实需要独立处置。不可变 Parquet 可保留历史输出，但“选择旧版本给下游”仍是新的交付决策。首期管理页不要提供重跑、取消、覆盖、删除、重新交付等写操作。

## DORA 与反馈：避免指标名称掩盖定义差异

**已核实的差异：DORA 当前官方指南采用五项软件交付指标：change lead time、deployment frequency、failed deployment recovery time、change fail rate、deployment rework rate。** 最后一项衡量生产事故导致的非计划部署比例；恢复时间专指失败部署后恢复。GitLab 当前 DORA 文档仍介绍四项，且其 lead time 从 MR 合并时刻计算，恢复时间来自 incident 开闭时间，不能直接认为与 DORA 官网的 commit-to-production 定义等价。[DORA 五指标指南](https://dora.dev/guides/dora-metrics/)、[指标演变](https://dora.dev/insights/dora-metrics-history/)、[GitLab 的计算口径](https://docs.gitlab.com/user/analytics/dora_metrics/)

**实施建议：CE 阶段先保留可信事件，再做自定义趋势图。** 采集提交、合并、制品、目标环境部署完成/失败、事故、恢复和补救部署的时间及关联 ID，明确服务范围、分母、统计窗口、时区、样本数与缺失值。生产部署次数不能用 pipeline 次数或数据处理批次数替代；没有真实生产部署记录时指标显示“尚无数据”，不是零失败率。初期人工登记优于无依据的自动估算。

业务反馈另看批次成功率、校验失败、数据新鲜度、人工返工和交付等待时间，不冒充 DORA。用反馈确定下一次改进的瓶颈，而非追求提交量、流水线数或个人排名；DORA 的价值流方法鼓励先识别等待和交接问题，小步改进并复查效果。[Value stream mapping](https://dora.dev/guides/value-stream-management/)、[Customer feedback](https://dora.dev/capabilities/customer-feedback/)

## 推荐推进顺序与验收证据

1. **梳理事实与交付目录。** 核对本地 CE 菜单、main CI、wheel 和现有运行记录；建立 Git SHA 到制品摘要的映射。验收看真实 pipeline 与制品，不以计划文档代替完成。
2. **先做本地只读演示原型。** 展示需求/代码交付与数据运行两个视角；标注演示状态与来源，校验空状态、失败和数据过期。原型不接凭据、不改业务状态。
3. **设计真实只读数据接入。** 明确 API、权限、脱敏、允许字段和运行边界；涉及认证、敏感数据或业务数据完整性时走 Standard Lane。验收要能沿一次批次追到代码、质量结果与交付记录。
4. **最后设计部署与操作。** 将部署代理、launchd 切换、人工/自动确认、回退和业务重跑分别评审。以目标机真实健康检查及失败演练验收，保留现有 Runner 的隔离约束。

本报告只完成资料调研与建议归纳；未创建 GitLab Issue/MR/Release、修改 Runner/Token、执行部署、连接业务库或发布前端。
