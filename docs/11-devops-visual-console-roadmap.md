# data-process 的 DevOps 与可视化管理落地路线

日期：2026-10-18。状态：调研后的建议方案，用户已选择“业务与 DevOps 两者整合的统一门户，先只读概览再逐步增加操作”；具体技术、安全与部署设计尚待确认。目标是用一次真实的可视化管理功能交付，串起需求、代码、验证、软件发布、运行反馈和改进。现有安全边界保持有效；本文不授予新的部署、令牌、网络或业务数据写入权限。

## 先把当前能力接成可追溯的交付过程

当前已有 GitHub 与本机 GitLab 双远端、受保护 main、受限 Shell Project Runner，以及 core_test → build_wheel → installed_wheel 的真实流水线。6585059712e900b74665e8c10f615740837e966c 是本轮读取的仓库基线；其验收记录见 .ci-reports/gitlab-final/pipeline.json（本地忽略文件）和 GitLab pipeline #3。代码中已有 CLI、运行队列、worker、质量校验、数据发布/回滚和本地健康告警，尚无 Web/API。

DevOps 的下一步要解决两件具体问题：操作员不必逐条敲 CLI 就能看懂产品和任务；一次功能变更要能追溯到需求、精确源码、通过验证的制品和真正运行的版本。前端正好成为这一流程的首个交付对象。

完整官方调研与版本/许可边界见 [GitLab DevOps 调研](research/2026-10-18-gitlab-devops.md)。GitLab 支持把 Issue 与 MR 关联，也能记录软件 Release 和环境部署；Release 记录、CI 成功和真正的应用部署是三种不同事件。[MR](https://docs.gitlab.com/user/project/merge_requests/)、[Release](https://docs.gitlab.com/user/project/releases/)、[Deployment](https://docs.gitlab.com/ci/environments/deployments/)。

```mermaid
flowchart LR
  I[需求与验收标准] --> M[变更与审查]
  M --> C[精确 SHA 的 CI 验证]
  C --> W[wheel 与校验清单]
  W --> S[隔离体验环境安装]
  S --> H[健康与页面验收]
  H --> F[问题与改进反馈]
  F --> I
```

其中“隔离体验环境安装”及其后续环境验收尚未实施；现有链路实际止于制品安装 smoke。普通 feature/MR 当前不会运行 CI，不能把图中的审查当成已具备合并前流水线门禁。

## 两类界面各自承担明确责任

建议让 GitLab 管理软件工程过程：需求、MR、源码、pipeline、测试报告、软件版本和环境记录。自建业务控制台管理数据产品：计算定义版本、任务实例、质量、正式数据交付、业务审计及 worker 状态。控制台以精确 commit 的链接关联 GitLab，后续再按需读取流水线摘要，不重做 GitLab 的 MR 编辑器或 Runner 管理页面。

概念在界面中要明确区分：

| 界面术语 | 项目中的实际含义 | 不能混同的对象 |
|---|---|---|
| 应用版本 | 完整 Git commit 对应的 wheel 与 manifest | SQL/计算定义 release_id |
| 计算定义版本 | Platform.release 生成的不可变计算快照 | GitLab 软件 Release |
| 任务运行 | 一个业务日期、来源、定义形成的 run | GitLab pipeline/job |
| 数据交付 | 质量校验后原子更新的正式 delivery 指针 | 软件部署/安装成功 |
| 应用回退 | 切回已验收的软件版本 | 数据回滚和数据库恢复 |

源码中的 Platform.release / publish / cancel / finish_run 继续拥有现有规则。Web controller 只验证请求、选择允许的产品、调用用例、转换响应，不能自己更新 deliveries 或复制状态机。worker 继续是独立执行进程，HTTP 请求不承担长时间计算。

## 第一版可视化范围建议

用户已确认第一版为统一门户：一个入口提供“数据运行”和“研发交付”两种视角，先只读概览，再逐步增加操作。GitLab 仍是工程记录的事实源，门户只聚合摘要与链接。

| 页面 | 第一版内容 | 验收要点 |
|---|---|---|
| 总览 | 产品、最近交付日期、队列与运行计数、worker 活性 | 数据来自实际只读查询；无配置/服务失活显示明确状态 |
| 运行列表 | 日期、状态、开始/结束时间、任务详情 | 服务端分页与筛选；空态、错误态、刷新时间可见 |
| 运行详情 | 质量摘要、受限日志、来源/定义标识 | 日志长度限制、HTML 转义、脱敏；不暴露原始记录和任意文件 |
| 正式交付 | 当前指针与业务审计 | 显示已发布事实，运行成功不能自动显示“已交付” |
| 研发交付 | 项目信息、main SHA、最近 pipeline/job 摘要、GitLab 深链接 | 只读服务端适配器；断连/超时显示不可用与最后更新时间，不能显示旧成功为当前成功 |
| 应用版本 | 本机实际安装 commit、验证报告和 GitLab 链接 | 老版本缺 build 信息时显示未知，不推断为最新 main；部署版本与仓库 main 分开展示 |

第一条端到端切片选“统一概览 → 产品/最近运行 → 详情 → 当前应用版本及其对应 GitLab pipeline”，先以专用合成数据环境验证。工程摘要按精确 SHA 关联，不能直接把最新 pipeline 归属于正在运行的旧版本。第一版只读查询不创建数据 home、不执行 init、monitor、check 全量扫描、不启动 worker，不因打开页面产生写入。

随后单独增加“提交与取消”；最后再增加带 expected 当前指针、原因和身份审计的发布/数据回滚。请求超时不能假设业务操作未发生，重试必须沿用幂等键；CAS 冲突保留原指针并提示刷新。业务操作不能提供任意 Shell、SQL、文件路径或通用数据库执行入口。

## 技术路线比较

| 路线 | 适用与成本 | 本项目建议 |
|---|---|---|
| FastAPI + 服务端模板 + 少量浏览器脚本 | Python API 与页面同源，静态资源可随 wheel 交付，无需 Node 构建链 | 推荐首版，满足列表、筛选、详情、轮询与后续表单 |
| React/TypeScript + Vite + FastAPI | 更适合复杂交互和独立前端协作；增加 Node 版本、锁文件、构建与制品打包验证 | 若目标包含系统体验前端工程，可选；当前 Runner 需扩展经验证工具链 |
| 仅使用 GitLab 自带界面 | 工程流程可视化最快，无业务页面开发 | 可立刻作为工程入口，无法覆盖运行/质量/数据交付操作 |

FastAPI 官方提供类型化 API/OpenAPI 与模板集成；Vite 需要独立前端构建流程。以上取舍基于本项目当前 Python wheel、单用户与小规模管理页面，属于工程建议，并非这些工具的能力上限。[FastAPI](https://fastapi.tiangolo.com/features/)、[模板](https://fastapi.tiangolo.com/advanced/templates/)、[Vite](https://vite.dev/guide/)。依赖版本、资源打包规则和最终页面设计留到实现规格确认时锁定。

## 按可验收切片推进

| 阶段 | 可交付结果 | 进入下一阶段的判据 |
|---|---|---|
| 0 调研与设计 | 本文、官方调研、首版页面/接口范围和访问边界 | 用户确认产品优先级、使用范围和首版设计 |
| 1 只读体验版 | 专用合成状态目录、只读 API 和上述核心页面 | 不产生业务写入；权限/路径/转义边界通过；浏览器真实交互及 wheel 外部安装通过 |
| 2 操作用例 | 提交、取消，再分步开放发布/回滚 | 身份/会话与 CSRF 校验、幂等、CAS 和完整审计通过；失败不会改变正式交付 |
| 3 软件交付体验 | 需求关联代码、精确 SHA 构建、隔离体验环境安装与验收记录 | 从 GitLab 制品安装可用页面；软件回退演练通过；数据状态保留 |
| 4 反馈改进 | 应用活性、任务失败/逾期、安装版本与问题关联 | 能通过一次失败演练形成可追踪的问题和修复记录 |

实现阶段涉及浏览器访问业务状态、会话身份和状态写入，采用 Standard Lane，设计、验证、独立审查与交付证据分阶段记录。当前仅写调研文档，不需要为文档单独启动代码交付门禁。

## 现有 Runner 和 CE 的约束要保留

当前流水线和 Runner 都限制 protected main；直接启用 MR pipeline 不会自动获得可运行的 Runner。最小起步方式是本地验证与 MR 人工审查、合并后 main CI；必须明确这不构成合并前自动门禁。要体验完整的合并前 CI，应另行设计不持有部署/业务权限的隔离验证 Runner，不能把当前 Runner 改成接收任意分支。[MR pipelines](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/)。

当前 Runner 无宿主目录、Docker socket、sudo，也看不到业务状态目录。因此无法直接安装宿主 launchd 服务或管理 Docker。首轮软件交付可采用操作者取回已验证 wheel、在新建隔离目录安装并验收，再记录真实结果；人工安装要明确写为人工步骤。后续可设计单独的最小权限拉取式发布执行器，但需审批目标、身份、目录、制品验证、环境串行锁和回退策略。环境记录 API 本身不会帮我们运行应用。[环境与部署](https://docs.gitlab.com/ci/environments/)。

CE/Free 的手动 job 和 protected main 不能等同于付费 protected environments/强制审批。体验阶段可使用受限执行器和操作留痕，但不宣称形成独立职责分离。[Protected environments](https://docs.gitlab.com/ci/environments/protected_environments/)。

## 接入真实状态前的访问边界

首版默认仅本机访问，使用合成环境；监听地址/端口在实施设计中确认。回环监听不等于完整访问控制，需设计 Host 校验、同源策略、会话访问、敏感字段筛选；写操作另加 CSRF 与身份审计。若转向局域网、多人或远程访问，先明确认证/TLS/角色范围，不静默扩大监听地址。

产品 ID 映射到服务端登记的 data home，浏览器不能传任意路径；查询数据库使用 mode=ro，产品目录缺失时返回未配置状态。现有 Platform.runs/audit 会一次返回全部记录，Web 适配需增加受限分页读取，不直接将无限列表/内部路径原样暴露。既有 SQLite schema、发布事务和业务状态不因页面改造而改变。

首版统一门户通过服务端只读适配器获取固定项目的 main SHA、最近 pipeline/job 摘要；选择项目范围只读身份，拟采用 read_api 与可满足查询的最低项目角色，在实施前验证权限。不可把现有 api/write_repository bot 凭据交给 Web 应用。新只读令牌的创建、期限和托管列入 Standard Lane 安全规格；未配置时显示“GitLab 未连接”及固定链接，不编造状态。浏览器只请求同源后端，不持有 GitLab token，不转发任意项目/URL，不提供 pipeline/job 的触发或重试接口。秘密只在服务端；前端 bundle、日志、Git 和 artifact 均不得含凭据。[Project access tokens](https://docs.gitlab.com/user/project/settings/project_access_tokens/)。

## 用一次真实功能变更体验闭环

以“运行列表增加状态筛选”为样例：在 GitLab 记录需求和边界用例，关联实现与审查；本地验证后按当前允许的流程进入 main，由真实 CI 生成绑定 SHA 的 wheel。取该制品安装到隔离体验环境，用浏览器验证筛选、分页、空态与错误态，并记录实际运行版本。引入一个受控故障后验证错误可见、可回退到上一软件版本，再形成修复记录。每个阶段交付实际结果，避免只有 job 名称而没有安装/验证行为。

目前先观察 CI 时长、通过率、交付耗时及问题关闭过程。DORA 当前官方为五指标；生产部署频率、失败恢复等需要真实部署事件定义，体验环境的测量单独标记，不把 pipeline 次数充作生产部署频率。[DORA 指标](https://dora.dev/guides/dora-metrics/)。
