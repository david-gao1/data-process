# GitLab CI 本地验收记录

记录日期：2026-10-15。环境：此用户 Mac，macOS 27.0.1、Apple M3 Max arm64；本地 Python 3.11.8。以下结果不是 Linux Runner 或真实 GitLab pipeline 的执行记录。

## 已执行并通过

- `.venv/bin/python .ci/check_config.py`：7种workflow、5种手动作业条件、重复YAML键与artifact白名单检查通过。不是服务端CI Lint。
- `.venv/bin/python -m pytest -m 'not macos' --junitxml=.ci-reports/junit.xml -v`：50 passed、1 deselected；原始摘要见pytest-core.txt。
- `.venv/bin/python -m pytest -m macos -v`：1 passed、50 deselected；只检查launchd配置，没有加载服务。
- `.venv/bin/python -I -m data_process.smoke`：两个合成产品闭环通过，见source-smoke.txt。
- `.venv/bin/python .ci/build_wheel.py`：从干净提交9dabc70f7220dcef54887b67613f1b4d7a0c3f43的Git对象构建；manifest记录版本、锁文件、wheel及运行依赖文件SHA。见wheel-manifest.json。
- 独立`.wheel-venv`按`dist/runtime-requirements.txt`以`uv pip install --require-hashes`安装运行依赖，再安装wheel，最后以`python -I -m data_process.smoke --expect-commit ...`验证：每日活跃与零售两个产品均通过计算、质量检查、发布、查询及幂等重跑。见installed-smoke.json。无网络业务输入，无launchd操作。
- `sh -n .ci/bootstrap.sh`通过。补充在官方slim镜像中安装git，避免只有Runner helper含git而构建job失败；该安装分支尚待Linux环境执行。

原安装工具会话46943在连接中断后失效；已核查旧安装进程不存在，再续装已有独立venv。续装和安装后验证会话5929退出码0。未将会话失效误报为测试成功。

## Docker及未完成项

已安装Docker Desktop 4.37.2。`docker desktop start --timeout 30`退出1并报告context deadline exceeded；随后`docker desktop status`退出1，未发现Docker进程。Gatekeeper只读检查返回accepted / Notarized Developer ID；未发现Docker崩溃报告。当前不能确定是初始化、系统提示还是应用兼容性，不能归因为权限不足。

需要用户通过Finder打开Docker并查看原生界面；协议、管理员提示和密码输入由用户亲自处理。没有读取或保存聊天密码，没有使用sudo，没有更改Gatekeeper或隐私权限。

GitLab compose已通过静态配置校验；官方19.4.2 CE原生arm64元数据已记录在infra/gitlab/image-platforms.json。未拉取镜像、未启动GitLab、未创建管理员凭据、未创建项目或注册Runner。首次启动持久管理员凭据、Runner认证及Docker执行权限仍需对应动作的明确确认。

尚未执行：Docker资源分配实测、Linux Python3.11.17测试、GitLab服务端CI Lint、真实Runner流水线、JUnit/artifact服务端读取、GitLab备份恢复。没有将CI准备当作CI上线。没有推送当前提交，没有公开部署。
