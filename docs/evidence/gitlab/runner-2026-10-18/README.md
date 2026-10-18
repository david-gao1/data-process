# 本机 GitLab + 专用 Shell Runner 验收（2026-10-18）

实际已完成：私有 root/data-process、专用 Shell Project Runner、双远端 main 同步与真实三项 CI。不是离线模拟结果。未运行 UCI manual，未部署应用。

## 可核对的交付

- 验收源码：541796d45f110e5a864cafef2bc2fe2a2425383d。
- [真实流水线 #2](http://127.0.0.1:8929/root/data-process/-/pipelines/2)：core_test #4、build_wheel #5、installed_wheel #6 均 success；JUnit 50 tests、0 failures/errors/skipped。macOS 本地完整测试另为 51 passed。
- GitHub origin 和 gitlab-local 的 main 均已通过 ls-remote 核对为该完整 SHA。此次用户明确追加双远端同步要求；后续更新按当次授权及 agent.md 检查流程执行。
- API 下载真实 artifacts 后逐项检查 zip 成员，仅 JUnit/source-smoke/installed-smoke、wheel/manifest/hash requirements。manifest commit、wheel SHA256、requirements SHA256、installed-smoke 内置 commit 均匹配。脱敏副本见 pipeline-2/，未把 wheel 二进制再次纳入 Git。
- pipeline.json 记录精确 commit、job ID/URL、artifact 成员和归档 hash。后续文档提交会产生新 SHA，必须另查对应真实流水线，不能把 #2 冒充最终 HEAD 结果。

## 安全与资源实测

runtime.json：Runner 容器限制 2 CPU/2 GiB，privileged=false、no-new-privileges；仅配置/工作两个命名卷，无 bind mount/socket。concurrent=1/limit=1，shell executor；控制进程读取 root 0700/0600 认证卷，job UID1000、无 sudo、不可读配置、不可改 Runner 二进制。既有 GitLab 和两个 Kubernetes 容器运行中，未重启 Docker/既有服务，未删数据卷。

project-permissions.json：项目 private、shared_runners_enabled=false、keep_latest_artifact=false；Runner project_type，只有项目1，locked=true、run_untagged=false、access_level=ref_protected，固定 tag=data-process-local-shell；main 禁 force-push，仅 Maintainer push/merge。CI workflow 额外只允许 protected main push/web。没有管理员 PAT；项目 bot token 为 api/write_repository、Maintainer、30 天期限，仅用于本机项目操作，不传 job。

Runner 官方 19.4.0 linux-arm64 来源及校验见 runner-download.json。二进制 SHA256 与官方 release.sha256 一致；运行版本确认19.4.0。CI 静态及 main dry-run 使用目标实例实际 GitLab Lint，均有效；main dry-run 只有三项 job。

## 已定位并修复的问题

1. 官方 Debian HTTP 主索引多次超时，同容器 HTTPS 请求成功。镜像使用官方 HTTPS 源、进程级 IPv4/30秒 timeout，索引9秒完成；未改全局代理/DNS/daemon。
2. pipeline #1（c067110）在 prepare environment 失败，尚未执行测试。默认 .bash_logout 的 clear_console 使 `set -eo pipefail; ...; exit 0` 非交互 login shell 返回1；无显式 exit 则0。清空该默认 hook 后相同复现返回0，后续 pipeline #2 全通过。镜像和既有 Runner 工作卷均处理；没有删除卷。官方说明：https://docs.gitlab.com/runner/shells/#shell-profile-loading 。
3. Compose 配置卷由安全写入步骤预建，需声明 external=true/name，避免误管理或重建现有凭据卷。

独立静态审查见 review.md。历史 bootstrap 证据和用户原未提交文档已一并保留、提交。密码文件只按用户要求放本地忽略目录、0600；报告不含密码/令牌，不把文档当永久授权。
