# 此Mac的GitLab安装准备

本机已测：Apple M3 Max arm64、14逻辑核、36GiB物理内存、约338GiB可用盘。官方Docker Hub `gitlab/gitlab-ce:19.4.2-ce.0`同时提供linux/arm64与linux/amd64，元数据见image-platforms.json；此compose固定arm64，不使用不明第三方镜像或默认x86仿真。Docker Desktop已经安装，但守护进程当前未启动；界面启动调用中断，没有重复提交未知结果的动作。

## 边界与需要确认的动作

compose仅准备，不代表已部署。启动server会初始化持久配置/数据库和自动生成root初始密码；这是持久凭据创建，需明确确认后才能运行up。密码不得出现在聊天、CI日志或版本库，首次登录和改密码由用户在安全界面接管。当前没有注册Runner或创建token。

默认只映射127.0.0.1:8929到server的8929；没有SSH端口、LAN/公网映射、privileged、宿主Docker socket或宿主目录挂载。仅三个明确命名的Compose volume存配置/日志/数据；restart=no，不自动设为登录常驻。HTTP仅限本机回环开发评估，不作为远程生产TLS方案。内网Runner将使用Docker网络内gitlab:8929，clone_url需要内部地址覆盖，不能把job内127.0.0.1误当宿主。

官方单节点基线为8vCPU/16GiB，受限配置最低8GiB；存储还包括应用40GB、PostgreSQL5–12GB、仓库、镜像、artifact和备份。此开发配置限制6CPU/10GiB，单Puma与较低Sidekiq并发，不宣称达到正式生产基线。Docker VM必须先分配足够内存（建议至少12GiB以留出一个CI job空间），会减少Mac其他应用可用资源；不得在不足时靠swap硬启动。先核对实际Docker配置与系统内存压力，再向用户说明必要资源调整。

## 尚未执行的审查命令

```bash
# 仅校验/查看，不启动：
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml config -q
# 以下需确认server启动及初始持久凭据生成后执行：
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml pull
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml up -d
# 健康，不输出密码或日志全文：
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml ps
curl --fail --max-time 10 http://127.0.0.1:8929/-/health
```

GitLab Server保存仓库、MR和pipeline；Runner负责执行CI；data-process worker负责业务数据运行。三者分工不能混淆。CE开源安装不需要购买服务；Docker Desktop如果出现未接受的法律条款，由用户确认，不能替用户点击同意。

## Runner选择与权限

优先CI配置面向Linux Docker executor。它不要求job privileged、DinD或向job暴露socket，但Runner控制进程本身必须有某个Docker daemon管理权限。不得把“job不挂socket”误写成“Runner不需要Docker权限”。

确认前比较两种方案：
1. 官方Runner连接专用Docker执行环境，project-scoped认证、tag=linux-docker、concurrent=1，job不挂宿主目录/socket。持久认证及Docker控制权限必须逐动作批准；不得随手把宿主socket挂入通用Runner容器。
2. 若不愿授予宿主Docker控制，可在隔离官方Python基础容器内运行受限shell Runner（官方Runner二进制），不挂socket、无privileged；这不是Docker executor，需显式改用适配的shell流水线，并接受同Runner作业隔离较弱、仅可信项目的限制。不能默认切换并宣称等价安全。

尚未安装或注册任一Runner。目标项目建议本机私有data-process，需在用户登录后核实实际namespace和完整URL；GitHub origin保留，新GitLab远端另命名。推送和注册只按本次明确授权操作，不沿用先前GitHub授权。

## 启停、备份、恢复、卸载

确认安装后，stop停止、start恢复；down删除容器/网络但保留volume。GitLab备份使用官方gitlab-backup工具，同时单独保留配置与gitlab-secrets.json；秘密仅存受限备份目录，不输出聊天、不放artifact。恢复需匹配GitLab版本/edition，先在隔离环境验证再替换。尚未实际生成备份，不能称恢复通过。

```bash
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml stop
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml start
docker compose -p data-process-gitlab -f infra/gitlab/compose.yml down
```

彻底卸载需先检查备份并得到删除持久数据的单独确认，才可删除三个data-process-gitlab前缀volume；不提供默认down -v脚本，不删除其他Docker服务或镜像。Runner撤销认证/停用也须分别处理。

来源：GitLab官方[安装](https://docs.gitlab.com/install/docker/installation/)、[资源要求](https://docs.gitlab.com/install/requirements/)、[Runner Docker](https://docs.gitlab.com/runner/executors/docker/)、[备份](https://docs.gitlab.com/administration/backup_restore/backup_gitlab/)。所有描述为本机评估范围，不是HA或公网部署。
