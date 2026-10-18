# 此Mac的GitLab安装与运行状态

历史准备记录（2026-10-16，资源与启动状态以以下2026-10-18实测为准）：Apple M3 Max arm64、14逻辑核、36GiB物理内存、约338GiB可用盘。官方Docker Hub `gitlab/gitlab-ce:19.4.2-ce.0`同时提供linux/arm64与linux/amd64，元数据见image-platforms.json；此compose固定arm64，不使用不明第三方镜像或默认x86仿真。Docker Desktop 4.37.2已恢复，2026-10-16在沙箱外获准查询daemon27.4.0成功；沙箱内无法连接不能当作daemon停止。Linux aarch64/Python3.11.17的50个核心测试和独立wheel闭环已经通过，证据见docs/evidence/gitlab/linux-2026-10-16。VM仅约8.72GiB，尚不足GitLab10GiB配置及现有容器，等待提高内存/重启和首次管理员凭据初始化的明确确认；GitLab仍未启动。

2026-10-18：用户明确批准首次初始化，GitLab CE 19.4.2 arm64已启动并healthy；登录入口为 http://127.0.0.1:8929 。Docker VM实测14CPU/17.29GiB，本次未调整设置或重启daemon；只打开原已安装Docker Desktop。容器6CPU/10GiB、仅回环端口、三个专用卷配置已实测核对，两个已有Kubernetes容器保持运行。普通pull的registry EOF通过同一官方仓库的进程级IPv4下载及逐层摘要校验解决，没有第三方镜像。证据见[首次初始化验收](../../docs/evidence/gitlab/bootstrap-2026-10-18/README.md)。用户已完成首次登录/改密，私有 root/data-process 已创建；Runner 接入见下文与最新验收记录。

## 边界与需要确认的动作

本次server首次初始化已得到用户明确确认并完成，三个持久卷及管理员初始凭据已生成。后续新实例首次初始化仍需明确确认。密码不得出现在聊天、CI日志或版本库，首次登录和改密码由用户在安全界面接管。2026-10-18 本次接入的项目令牌/Runner 按用户明确授权创建；后续操作不从本手册推断永久授权。

默认只映射127.0.0.1:8929到server的8929；没有SSH端口、LAN/公网映射、privileged、宿主Docker socket或宿主目录挂载。仅三个明确命名的Compose volume存配置/日志/数据；restart=no，不自动设为登录常驻。HTTP仅限本机回环开发评估，不作为远程生产TLS方案。内网Runner将使用Docker网络内gitlab:8929，clone_url需要内部地址覆盖，不能把job内127.0.0.1误当宿主。

官方单节点基线为8vCPU/16GiB，受限配置最低8GiB；存储还包括应用40GB、PostgreSQL5–12GB、仓库、镜像、artifact和备份。此开发配置限制6CPU/10GiB，单Puma与较低Sidekiq并发，不宣称达到正式生产基线。Docker VM必须先分配足够内存（建议至少12GiB以留出一个CI job空间），会减少Mac其他应用可用资源；不得在不足时靠swap硬启动。先核对实际Docker配置与系统内存压力，再向用户说明必要资源调整。

## 当前只读检查命令

```bash
# 仅校验/查看：
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml config -q
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml ps
# 默认监控IP allowlist保留；从容器loopback检查：
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml exec -T server curl --fail --max-time 10 'http://127.0.0.1:8929/-/readiness?all=1'
# 宿主机访问可用性：
curl --fail --max-time 10 --output /dev/null http://127.0.0.1:8929/users/sign_in
```

GitLab Server保存仓库、MR和pipeline；Runner负责执行CI；data-process worker负责业务数据运行。三者分工不能混淆。CE开源安装不需要购买服务；Docker Desktop如果出现未接受的法律条款，由用户确认，不能替用户点击同意。

## Runner选择与权限

已按用户指定选择专用容器 Shell Project Runner，不接 Docker executor。runner-compose.yml 独立管理 Runner，禁止通过修改 server compose 来重建 server。Runner 2 CPU/2 GiB、concurrent/limit=1；无 host bind/socket、privileged=false、no-new-privileges，root 控制进程只为降权到 gitlab-runner 作业用户，作业无 sudo。配置卷 root-only，与 UID1000 的工作卷分离。

构建使用已验证的官方 Python 3.11.17 arm64 基础镜像及官方 Runner 19.4.0 二进制；下载 URL 和 SHA256 见 ../../docs/evidence/gitlab/runner-2026-10-18/runner-download.json。将 Dockerfile 和已核验二进制复制到无秘密的临时 build context 后 build，不以整个项目作为上下文。

```bash
# 镜像已构建且专用配置卷就绪后，仅操作 Runner：
docker compose -p data-process-gitlab-runner -f infra/gitlab/runner-compose.yml up -d --pull never
docker compose -p data-process-gitlab-runner -f infra/gitlab/runner-compose.yml ps
```

Runner URL/clone_url 均使用网络内 http://gitlab:8929/，不能使用容器内 127.0.0.1。只接受 root/data-process 的 protected main、tag data-process-local-shell；locked、run_untagged=false，关闭 shared runners。Shell 的同项目 job 共享工作卷，只适用于可信 main；不是多租户沙箱。令牌绝不放 Compose environment 或命令行，禁止输出 config.toml/完整 inspect 环境/原始日志。

GitHub origin 保留，新增 gitlab-local；用户本次追加要求两边同步 main。后续每次按当次授权显式推两边并核对 SHA，操作说明不是永久授权。

## 启停、备份、恢复、卸载

确认安装后，stop停止、start恢复；down删除容器/网络但保留volume。GitLab备份使用官方gitlab-backup工具，同时单独保留配置与gitlab-secrets.json；秘密仅存受限备份目录，不输出聊天、不放artifact。恢复需匹配GitLab版本/edition，先在隔离环境验证再替换。尚未实际生成备份，不能称恢复通过。

```bash
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml stop
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml start
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml down
```

彻底卸载需先检查备份并得到删除持久数据的单独确认，才可删除三个data-process-gitlab前缀volume；不提供默认down -v脚本，不删除其他Docker服务或镜像。Runner撤销认证/停用也须分别处理。

来源：GitLab官方[安装](https://docs.gitlab.com/install/docker/installation/)、[资源要求](https://docs.gitlab.com/install/requirements/)、[Runner Docker](https://docs.gitlab.com/runner/executors/docker/)、[备份](https://docs.gitlab.com/administration/backup_restore/backup_gitlab/)。所有描述为本机评估范围，不是HA或公网部署。
