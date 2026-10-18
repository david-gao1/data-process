# 本机 GitLab 项目与 Shell Runner 接入

## Intent / Spec（Standard Lane）

2026-10-18 用户已批准在现有 GitLab 创建私有 root/data-process、官方 Runner 安装、项目专属令牌持久配置、CI 修改提交及推送。随后明确要求同时推送 GitHub origin 与 gitlab-local。仅 main 和可达 Git 历史；不推业务数据、密码、令牌，不运行真实 UCI 手动作业，不部署应用。既有 GitLab 和 Kubernetes 不重启、不重装、不删卷。

固定方案：官方 Python 3.11.17 arm64 基础镜像内安装官方校验通过的 Runner；shell executor，单并发，容器 2 CPU/2 GiB，无特权、无宿主 bind mount/socket、无 sudo。控制进程读取 root-only 配置卷，作业降权 gitlab-runner；工作卷与配置卷分离。项目 Runner locked、protected、专属 tag、run_untagged=false，CI workflow 仅受保护 main 的 push/web。仅受信任项目，Shell executor 不提供每个 job 的强隔离。

## Plan / gates

1. 复核 Git、说明、现有卷与容器，复用 root 浏览器会话，创建私有空项目（先查重）。
2. 下载官方 Runner 与 SHA256 清单，核验固定版本和架构，构建专用镜像；只增加 Runner 服务与两个专用卷。
3. 使用现有实例权限执行项目范围配置；令牌直接写受限配置卷，不输出或放入参数；不创建管理员 PAT。保护 main，关闭共享 Runner 和 untagged，锁定项目。
4. 修改 CI bootstrap 为非 root 预装工具检查，workflow 限 main/protected，验证 Shell 重用 checkout 清理；保留 wheel 和报告白名单。
5. 本地测试、目标服务端 CI Lint、检查待推 Git 对象不含业务数据/凭据；提交后向两远端显式推 main。
6. 核对两远端准确 SHA 与该 SHA 的真实三项 job、JUnit、wheel manifest；独立复核配置/权限/数据边界。
7. 将验证证据与排障记录写入 agent.md/手册并同步；最后一笔文档提交也验证真实流水线。

## Completion criteria

两远端 main 等于本地 HEAD；core_test/build_wheel/installed_wheel 全成功；制品 commit/hash 相符；public_retail_manual 未运行；Runner 限制与认证卷权限有实测证据。未满足不得宣称完成。凭据位于 .local/gitlab/credentials.json，0600，由 .git/info/exclude 忽略；文档不是永久授权。
