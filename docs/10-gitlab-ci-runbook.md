# GitLab CI/CD 准备与接入手册

当前状态：项目内CI、wheel和本地验证准备；目标已明确为此Mac自建GitLab，尚无可用GitLab URL/项目/Runner认证。没有将新配置推送到GitHub或GitLab。服务端CI Lint和真实Runner结果需接入后产生，离线校验不能替代。

## 流水线和Runner

.gitlab-ci.yml按MR/分支切换，web可手动启动，schedule/API/tag不自动执行。默认image固定python:3.11.17-slim-bookworm；已只读核对官方镜像有amd64与arm64。Runner需Docker executor、tag linux-docker（可由项目变量DP_RUNNER_TAG改为实际tag），建议单并发、2vCPU/2GiB job起步；不需要job privileged、DinD、Docker socket或生产目录挂载。

bootstrap在slim镜像缺git时从Debian签名软件源安装git（Runner helper完成clone不代表job镜像有git），固定uv0.10.9，uv.lock冻结运行/测试/构建依赖，禁自动下载Python，使用镜像既有3.11.17。构建backend及其传递依赖在build组锁定。默认job不读真实源、不调用launchctl、不产生常驻服务。

| job | 责任 | 交付 |
|---|---|---|
| core_test | 离线规则/50个POSIX测试case/JUnit/固定双产品smoke | JUnit与只含验证状态的小报告，7天 |
| build_wheel | 测试成功后只从当前commit白名单文件构建 | 版本带完整SHA的wheel、manifest、带hash运行依赖，14天 |
| installed_wheel | 独立venv安装该artifact，从仓库外以-I运行 | 验证内置commit、资源与双产品闭环，7天 |
| public_retail_manual | 默认分支web pipeline显式RUN_PUBLIC_RETAIL=1后手动运行 | 有限UCI接入；仅成功/失败阶段状态，3天 |

GitLab Server保存/协调，Runner执行job，业务worker执行数据run。Runner的Docker管理权限属于单独控制面权限，即使job没socket也不能说无需授权。

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

本地Python3.11.8的结果不能当作Linux/Python3.11.17已执行。Docker daemon未运行时不会启动它来冒充Linux验证。macos标记仅检查launchd plist合法性，不启动已有服务；Linux默认明确排除它。已有进程/文件锁/取消/恢复测试是POSIX，仍需目标Linux Runner实际执行确认。

wheel从git对象读取src/data_process、definitions、source registry和锁文件，不复制忽略的本地文件。版本为0.1.0+g<完整commit SHA>，manifest绑定wheel SHA与requirements SHA；安装前对照CI_COMMIT_SHA。包内自带SQL、来源配置与锁文件，离开checkout也可release。数据状态ROOT与包内资源ASSET_ROOT分离，运行目录由--home/DP_HOME显式指定；manifest还记录包的platform_build来源。

软件wheel本身不含DuckDB的目标平台二进制依赖，必须安装配套runtime-requirements；离线部署需为目标架构另备经过hash校验的wheelhouse。本轮没有发布PyPI或Package Registry。

## Artifact与真实数据边界

不归档整个仓库、venv、.ci-state、数据库、raw、sources或candidates。UCI真实查询结果也不上传artifact：原始报告重定向私有临时文件，public_status只保留通过/失败阶段、退出码与历史回放标志，然后after_script删除私有数据与备份。网络下载失败与业务E2E失败分开，不把网络波动变成核心测试失败；手动job非阻断且没有自动retry，不代表失败被验证为成功。

artifact仅developer可下载，expire_in明确。GitLab项目“保留最新成功artifact”设置可能让文件保留超过期限；自建实例接入时需核对。默认分支变量/保护规则与fork MR权限也需由实例实际策略确认。没有任何生产凭据进入默认测试job。

## 目标实例接入验收

1. 先按infra/gitlab/README确认Docker与资源；server首次启动产生持久管理员凭据需要明确确认，用户处理首次登录/改密码。
2. 在实际登录身份下确认私有项目namespace/完整URL，再创建项目并添加独立gitlab-local远端；保留GitHub origin，不静默迁移。
3. 选Runner隔离方案并逐动作批准project-scoped认证和所需执行权限；不可用无关全局Runner或宿主广泛挂载。
4. 在目标GitLab运行CI Lint，验证当前实例支持artifacts:access等关键字，模拟MR/分支/web规则。不通过则先修正，不能用本地PyYAML代替。
5. 得到本次目标推送授权后推送；核对服务端SHA，观察core/build/installed jobs真正通过、JUnit和artifact可取、无重复pipeline，再对手动作业单独决定是否运行。

## CD部署契约（尚未实施）

没有伪deploy echo、远程SSH、sudo服务安装或公开部署。后续部署job必须指定目标机器/账号/状态目录、受保护environment和人工审批；只消费本pipeline验证过的SHA制品，核对manifest，先备份状态，再安装并执行目标机健康/只读查询。失败保留旧软件及delivery指针，按旧wheel和备份恢复；不能直接用CI产物包覆盖生产数据目录。当前缺少目标与审批，所以CI准备只交付软件artifact，不宣称已部署。

自建资源与启停/备份/卸载说明见[本机GitLab准备](../infra/gitlab/README.md)，官方依据见[ADR](adr/003-gitlab-ci-delivery.md)。
