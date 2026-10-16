# Linux 实际执行验收

2026-10-16，在此Mac的Docker Desktop27.4.0运行官方Python镜像，Linux aarch64 / Python3.11.17。命令退出0。固定源提交8a4ff0ef7cde568d33df5038078f618edff32708，无生产输入。

镜像：`python:3.11.17-slim-bookworm`，拉取registry digest `sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89`；实际arm64 image ID `sha256:3c50954f1f466ff97efcbe7678f38adf0401eb3ddda4966e04f5be9cd6c71aed`。

执行步骤见verify.sh：Debian签名软件源安装git；从只读Git bundle克隆到容器/work；实际执行.ci/bootstrap.sh、冻结安装、50个核心测试、源码双产品smoke、基于commit的wheel构建、独立venv带hash依赖安装和隔离wheel smoke。Git和uv冷下载约77kB/s，冷启动明显超过原10分钟预算；配置上限已另调30分钟，尚未经过GitLab服务端校验。

结果：50 passed、1 deselected（macOS专用）。源码和wheel两个产品均passed/idempotent；wheel版本、内嵌commit及校验manifest一致。JUnit见junit.xml，环境、软件SHA和状态见各JSON。依赖安装用了网络，业务smoke本身没有外部数据网络操作。GitLab Server/Runner均未参与，不能称为真实pipeline通过。

容器仅2CPU、2GiB、256PID、no-new-privileges，无privileged、无socket、无端口、无其他项目目录挂载；输入bundle只读、结果目录可写，退出后--rm删除容器。现有Kubernetes/MySQL和volumes没有修改。

重现（从项目根；需Docker权限及网络）：先提交源代码，再创建专用输入/结果目录和`git bundle create .ci-state/linux-input/source.bundle HEAD`，复制此verify.sh为输入目录下verify.sh。执行：

```bash
docker run --rm --name data-process-linux-verification \
  --cpus 2 --memory 2g --pids-limit 256 \
  --security-opt no-new-privileges \
  --mount "type=bind,src=$PWD/.ci-state/linux-input,dst=/input,readonly" \
  --mount "type=bind,src=$PWD/.ci-state/linux-results,dst=/results" \
  python:3.11.17-slim-bookworm sh /input/verify.sh
```

未覆盖：GitLab CI Lint、Runner调度及作业间artifact传递、服务端JUnit/artifact权限、真实UCI手动作业、本机GitLab备份恢复。下一步仍需VM资源与首次凭据初始化确认。
