# GitLab CI/CD 准备与接入手册

当前状态（2026-10-18）：本机私有 root/data-process 与专用 Shell Project Runner 接入完成。真实流水线 #2 对 541796d45f110e5a864cafef2bc2fe2a2425383d 的 core_test/build_wheel/installed_wheel 全成功，Linux50项与macOS51项测试通过；下载 artifacts 验证了 commit 和 hash。GitHub origin 与 gitlab-local 已同步该 main；最终文档提交后的最新 SHA/流水线另行实测核对。详见 [接入验收](evidence/gitlab/runner-2026-10-18/README.md)。未运行真实 UCI manual，未部署。

## 流水线和Runner

.gitlab-ci.yml 只允许受保护 main 的 push/web；MR、feature、schedule/API/tag 均不执行。专属 tag 固定为 data-process-local-shell，不能由项目变量覆盖。Shell executor 在专用容器内运行；default image 对 Shell 不生效，因此已移除。工具由固定 Python 3.11.17 / Runner 19.4.0 / uv 0.10.9 镜像预装，job 不调用 apt、sudo 或全局 pip。concurrent=1，容器 2 CPU/2 GiB，无特权、无宿主 bind/socket，控制进程 root，job 降权 UID 1000；配置卷 root 0700/config.toml 0600，job 不可读。Shell 同项目作业共享环境，不提供每个 job 强隔离，只执行受信任的 main。

每个 job 使用 GIT_STRATEGY=clone / GIT_DEPTH=0，避免旧 .wheel-venv 和 dist 污染；uv.lock 冻结依赖、禁止自动下载 Python。默认 job 不读取真实业务状态、不调用 launchctl、不产生常驻业务服务。

2026-10-16本机Linux冷启动实测网络约77kB/s，单uv下载约5分钟，尚有Debian索引与DuckDB依赖；默认job上限因此由10分钟调整为30分钟，手动真实数据job由20分钟调整为40分钟以包含bootstrap。仍无自动job重试；业务worker自身超时不因此放宽。

| job | 责任 | 交付 |
|---|---|---|
| core_test | 离线规则/50个POSIX测试case/JUnit/固定双产品smoke | JUnit与只含验证状态的小报告，7天 |
| build_wheel | 测试成功后只从当前commit白名单文件构建 | 版本带完整SHA的wheel、manifest、带hash运行依赖，14天 |
| installed_wheel | 独立venv安装该artifact，从仓库外以-I运行 | 验证内置commit、资源与双产品闭环，7天 |
| public_retail_manual | 默认分支web pipeline显式RUN_PUBLIC_RETAIL=1后手动运行 | 有限UCI接入；仅成功/失败阶段状态，3天 |

GitLab Server保存/协调，Runner执行job，业务worker执行数据run。本次 Shell Runner 不持有 Docker daemon 管理权限，只有宿主操作者构建和管理专用容器。

## 可在本机先做的验证

```bash
uv sync --frozen --extra dev --group build --no-editable
.venv/bin/python .ci/check_config.py
.venv/bin/python -m pytest -m 'not macos' --junitxml=.ci-reports/junit.xml -v
.venv/bin/python -m pytest -m macos -v
.venv/bin/python -I -m data_process.smoke --output .ci-reports/source-smoke.json
# 下列构建要求所有源文件先形成干净本地commit；不自动commit或push：
UV_CACHE_DIR="$PWD/.cache/uv" .venv/bin/python .ci/build_wheel.py
DP_PYTHON="$PWD/.venv/bin/python" UV_CACHE_DIR="$PWD/.cache/uv" sh .ci/installed_smoke.sh
```

2026-10-16已在真实Linux aarch64/Python3.11.17容器执行50个核心测试和独立wheel双产品闭环并通过，见[evidence](evidence/gitlab/linux-2026-10-16/README.md)。这是本机容器验证，尚非GitLab Runner流水线或服务端CI Lint。此前Mac Python3.11.8结果另行保留。macos标记仅检查launchd plist合法性，不启动已有服务；Linux默认明确排除它。已有进程/文件锁/取消/恢复测试是POSIX，目标GitLab Runner仍需验证调度、作业环境和artifact传递。

wheel从git对象读取src/data_process、definitions、source registry和锁文件，不复制忽略的本地文件。版本为0.1.0+g<完整commit SHA>，manifest绑定wheel SHA与requirements SHA；安装前对照CI_COMMIT_SHA。包内自带SQL、来源配置与锁文件，离开checkout也可release。数据状态ROOT与包内资源ASSET_ROOT分离，运行目录由--home/DP_HOME显式指定；manifest还记录包的platform_build来源。

软件wheel本身不含DuckDB的目标平台二进制依赖，必须安装配套runtime-requirements；离线部署需为目标架构另备经过hash校验的wheelhouse。本轮没有发布PyPI或Package Registry。

## Artifact与真实数据边界

不归档整个仓库、venv、.ci-state、数据库、raw、sources或candidates。UCI真实查询结果也不上传artifact：原始报告重定向私有临时文件，public_status只保留通过/失败阶段、退出码与历史回放标志，然后after_script删除私有数据与备份。网络下载失败与业务E2E失败分开，不把网络波动变成核心测试失败；手动job非阻断且没有自动retry，不代表失败被验证为成功。

artifact仅developer可下载，expire_in明确。GitLab项目“保留最新成功artifact”设置可能让文件保留超过期限；自建实例接入时需核对。默认分支变量/保护规则与fork MR权限也需由实例实际策略确认。没有任何生产凭据进入默认测试job。

## 目标实例接入验收

1. 核对现有 server/Kubernetes 不被重建，保留三个 GitLab 卷；首次登录由用户完成。
2. 先查重，再创建私有 root/data-process，不初始化 README；保留 origin，新增 gitlab-local。
3. 本次用户已批准项目专属令牌及持久配置。使用本机容器内 GitLab 官方服务创建 project runner 与 30 天项目 bot token（api/write_repository，Maintainer），没有管理员 PAT。Runner token 通过私有进程管道写配置卷；项目 bot token 仅在宿主被忽略的 0600 文件，不传 job。
4. 核对 protected main、locked 项目 Runner、关闭 untagged/shared runners、专属 tag，以及 keep_latest_artifact=false。配置/trace 不得输出令牌。项目 bot token 可用于项目 API 与 main 推送，到期须按当次授权续建/轮换。
5. 服务端静态 Lint 后推送 main；再做 main dry-run 和真实三项 job 验收。校验两远端 SHA、manifest、wheel hash、JUnit。真实 UCI manual 和部署均不在本次范围。
6. 双远端没有原子提交保证：显式推两边，逐一 ls-remote；一边失败需报告并在同一授权范围修复，不 force-push 或静默改历史。

本地密码文件 .local/gitlab/credentials.json 为用户要求保留，仅主机 0600、父目录 0700，由 .git/info/exclude 忽略，不进 Git/镜像/artifact。不要 cat、打印、放命令参数或远端 URL；新登录使用安全界面。agent.md 只记位置和检查流程，不记录秘密，不构成永久授权。

## CD部署契约（尚未实施）

没有伪deploy echo、远程SSH、sudo服务安装或公开部署。后续部署job必须指定目标机器/账号/状态目录、受保护environment和人工审批；只消费本pipeline验证过的SHA制品，核对manifest，先备份状态，再安装并执行目标机健康/只读查询。失败保留旧软件及delivery指针，按旧wheel和备份恢复；不能直接用CI产物包覆盖生产数据目录。当前缺少目标与审批，所以CI准备只交付软件artifact，不宣称已部署。

自建资源与启停/备份/卸载说明见[本机GitLab准备](../infra/gitlab/README.md)，官方依据见[ADR](adr/003-gitlab-ci-delivery.md)。
