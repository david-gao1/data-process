# data-process 操作约定与已验证经验

本文件记录操作知识，不是永久授权。执行前读取当前用户要求、适用 AGENTS.md、Git 状态和最新证据；安全/认证工作采用 Standard Lane。2026-10-18 已检查项目及祖先路径，没有磁盘上的 AGENTS.md/agent.md；会话内个人约定适用。

## 项目与凭据边界

- 原仓库原地继续：HEAD 起点 68bb524，GitHub origin 保留。本机 GitLab 为 http://127.0.0.1:8929/root/data-process，私有，namespace root；账号 root。禁止重新建 Git 仓库、重装 GitLab、重启 Docker、清理数据卷或动两个现有 Kubernetes 容器。
- 用户要求双远端同步：origin 为 GitHub，gitlab-local 为本机 GitLab。每次有更新，在当次授权范围内向两者显式推相同 main，分别核对 ls-remote，禁止 force/mirror 推送，不静默修改历史。
- 密码按用户要求只存在 .local/gitlab/credentials.json（0600），父目录 0700，.git/info/exclude 忽略 /.local/。其内容不视为已验证登录成功。新登录优先现有浏览器会话；需要密码时由用户安全输入。禁止输出秘密、写入文档/命令参数/远端 URL/镜像/artifact。
- 项目 bot 凭据 .local/gitlab/project-access.json（0600）用于项目 API/Git，30 天期限；不是管理员 PAT。只记录位置，不输出内容。Runner 认证仅保留在专用配置卷，配置文件 root 0600、目录 0700，不传 job。到期或失效时按当次授权轮换，勿扩大范围。

## 接入与排障经验

- GitLab CE 19.4.2 arm64 保持现有 server：6 CPU/10 GiB、回环 8929、三个持久卷，restart=no。宿主登录页可用性和容器 loopback readiness 分开检查，外部监控 URL 404 不能推断服务故障，也不要放宽 allowlist。
- Docker registry EOF 曾通过官方源进程级 IPv4 和逐层 hash 验证解决，不能改用不明镜像或未经授权改 daemon。历史证据见 docs/evidence/gitlab/bootstrap-2026-10-18。
- 桌面控制若提示 Computer Use not active，先同次调用 getAXState 再执行操作；不能据此判断 GitLab/代码故障。项目创建复用了 Chrome 已登录 root 会话，空项目不初始化 README。
- 官方 Runner 19.4.0 linux-arm64 下载已与 release.sha256 核验，详见 runner-download.json。构建上下文仅 Dockerfile 和该二进制，不能包含 .local 凭据。
- 构建时 Debian HTTP 主索引多次超时；同容器 HTTPS 可达。Dockerfile 改为官方 HTTPS 源、进程级 ForceIPv4 与 30 秒 timeout 后索引 9 秒下载完成；不改宿主/Docker 全局网络设置。
- 首次 pipeline #1 在 prepare environment 失败，未进入业务测试。Debian 默认 .bash_logout 的 clear_console 在非交互 login shell + 显式 exit 0 时返回 1；同脚本无显式 exit 则 0。清空该 hook 后复现返回 0；镜像与既有专用工作卷均需处理，重建 Runner 不会覆盖已有卷中的 dotfile。依据 https://docs.gitlab.com/runner/shells/#shell-profile-loading 。
- Shell executor 忽略 image；工具应在镜像预装。CI job 非 root、无 sudo，不可 apt/pip 全局安装。GIT_STRATEGY=clone 避免持久工作区中的旧 wheel/venv 污染，GIT_DEPTH=0 保持完整历史。
- Runner 内 URL 和 clone_url 使用 gitlab:8929，不能写 127.0.0.1；控制进程 root 用于降权执行 job，认证配置卷和 UID1000 工作卷分离。Shell 只执行可信项目 main，不能视为 job 间强隔离。
- 受保护 main、Project Runner locked、专属 tag data-process-local-shell、关闭 untagged/shared runners；workflow 仅 protected main push/web。keep_latest_artifact=false，避免“最新成功”无限保留。

## 每次更新检查清单

1. 核对授权、远端 URL、当前分支、待提交差异与历史；不重置用户未提交改动。先检查凭据仍 ignored、0600；不把业务数据或秘密放 Git。
2. 修改前明确 lane/目标/验收。CI 修改运行 .ci/check_config.py、相关测试和服务端 Lint；真实 job 验证不能用本地结果代替。
3. 固定源码 commit 后构建 wheel，manifest/版本绑定完整 SHA；installed_wheel 从仓库外以 -I 验证。只允许 JUnit、小状态报告、wheel/manifest/hash requirements，禁止整个仓库、raw、数据库、业务状态 artifact。
4. 两远端先只读检查是否有并发更新，正常 fast-forward 推 main 后核对本地 HEAD=两远端 SHA。若部分失败，明确报告并修复，不宣称同步完成。
5. 检查该精确 SHA 的真实 core_test/build_wheel/installed_wheel，核对 JUnit、制品 hash 与 commit；不执行真实 UCI manual，不部署，除非另获明确授权。
6. 保留脱敏证据和失败原因，更新此文件与手册；文档变更形成新 commit 后，也需核对新 SHA 的流水线。不要把旧流水线当新 HEAD 成功。

接入计划、官方校验与验收证据：docs/evidence/gitlab/runner-2026-10-18/。

## 本轮真实验收

2026-10-18：commit 541796d45f110e5a864cafef2bc2fe2a2425383d 在两远端 main 相同，真实 pipeline #2 的三项 job 全通过，Linux50项、macOS51项；下载 artifacts 的完整 SHA/hash 与成员白名单验收通过。见 docs/evidence/gitlab/runner-2026-10-18/README.md 和 pipeline-2/pipeline.json。历史验收只对记录的 SHA 有效；读取本文件后仍须检查当前 HEAD/最新流水线。

## DevOps 与前端方向

2026-10-18 用户选择“业务与 DevOps 两者整合的统一门户，先只读概览再逐步增加操作”。官方调研见 docs/research/2026-10-18-gitlab-devops.md，落地建议见 docs/11-devops-visual-console-roadmap.md。软件应用版本、计算定义版本、业务 run、GitLab pipeline、数据 delivery 必须区分。当前 main-only Runner 不能直接承接普通 feature/MR 测试或宿主部署；不为实现 DevOps 而放宽既有隔离。Web 真实接入与访问控制按 Standard Lane 设计；不将此方向记录当作新增令牌、部署或业务写操作的批准。
