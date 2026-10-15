# ADR-003：GitLab CI 与可验证交付制品

2026-10-15；本轮仅项目内准备，GitLab地址/目标机器/Runner尚未确认。禁止把配置文件存在等同服务端流水线通过；不沿用先前GitHub push授权，不推送或部署。

## 目标与职责

GitLab Server管理仓库、MR、pipeline与artifact；Runner领取job并在executor运行。数据平台自己的worker执行业务run，两者不是同一个调度器：CI验证软件，业务worker执行已批准的数据生产。

优先Linux Docker executor，非privileged，无DinD、无Docker socket和生产数据挂载。固定Python补丁版本、uv与uv.lock；构建工具进入锁定依赖组。仅GitLab实例真实CI Lint可验证服务端语义；本地检查只覆盖YAML结构、选定规则场景和artifact边界。

## 流水线契约

- 分支push无MR时执行；存在MR的push不再开分支pipeline，转由merge_request_event执行；web手动pipeline允许，schedule/API/tag默认不执行。规则按官方顺序，避免“push+MR”重复。
- 必需job：POSIX离线pytest与JUnit、固定小样本双产品E2E；不启动launchd，不接入真实上游网络。
- 构建job：仅上游测试成功后，白名单打包Python wheel、内置SQL/来源配置/依赖锁，PEP440版本带完整commit SHA，另附校验清单和带hash的runtime requirements。
- 制品验证job：独立venv安装该wheel而非源码，从仓库外工作目录运行smoke，校验内置commit与SHA、双产品产出和正式查询。只有这个job通过才满足制品可运行条件。
- UCI job：仅默认分支web pipeline显式变量RUN_PUBLIC_RETAIL=1时显示为手动、非阻断job。有限下载，网络失败与业务校验失败分开标记；不把raw、数据库、sources/candidates或业务查询结果上传artifact。
- artifact白名单仅JUnit、软件wheel/manifest/runtime requirements与脱敏验证状态；有限保留期并限制developer下载。GitLab“保留最近成功artifact”设置可能超出expire_in，实例接入时核对。
- 不加伪deploy job。目标机、服务身份、目录、审批与回滚未知，CD只到“已构建并独立验证的软件制品”。远端部署需单独明确目标与授权。

## 代码变更必要性

现包依赖cwd中的definitions/uv.lock/sources；离开仓库安装不能可靠release。将运行资源打包并将资源位置与状态ROOT分开。平台数据库/原始数据/现有运行目录不进入wheel；旧release中的快照不修改。

## 官方资料（访问2026-10-15）

- [GitLab workflow rules](https://docs.gitlab.com/ci/yaml/workflow/)：MR与分支切换、CI_OPEN_MERGE_REQUESTS。
- [JUnit reports](https://docs.gitlab.com/ci/testing/unit_test_reports/)：reports:junit展示结果，本身不替代测试退出码。
- [Docker executor](https://docs.gitlab.com/runner/executors/docker/)：镜像与Runner责任，普通Python job无需privileged或DinD。
- [Job artifacts](https://docs.gitlab.com/ci/jobs/job_artifacts/)：访问与保留；不能归档整个工作目录。
- [CI Lint API](https://docs.gitlab.com/api/lint/)：最终需在目标实例校验include/rules语义与版本兼容。
- [uv GitLab integration](https://docs.astral.sh/uv/guides/integration/gitlab/)：锁依赖与uv缓存。
- [Python 3.11.17](https://www.python.org/downloads/release/python-31117/)：固定CI补丁版本；本机现有3.11.8与Linux目标验证必须分别报告。

## 自建边界

只准备要求清单；不安装GitLab，不启动Docker，不注册Runner、不创建凭据或改变网络。Mac上容器运行的是Linux VM，ARM GitLab软件包支持不能推导所有Docker标签都有arm64 manifest；需按选定版本实测镜像架构、资源与网络。正式部署优先受支持Linux主机，Mac仅明确标注本地评估用途。


目标更新：用户随后明确授权安装在此Mac。只读确认M3 Max arm64、36GiB和338GiB可用盘，官方CE19.4.2存在arm64 manifest。Docker Desktop原生启动调用因传输中断未确认，daemon仍未运行；请求用户完成Docker界面初始化/授权。准备server compose仅回环8929，首次启动生成持久管理员凭据仍单独确认，Runner认证/权限仍单独确认。
