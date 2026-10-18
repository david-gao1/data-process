# 本机 GitLab 首次初始化验收（2026-10-18）

用户明确批准首次初始化后，已在迁移后的项目目录启动官方 GitLab CE 19.4.2 arm64。容器 `data-process-gitlab-server-1` healthy，restart_count=0，无 OOM；宿主机 `http://127.0.0.1:8929/users/sign_in` 返回200。容器内 health、liveness、readiness?all=1 均返回200，依赖检查全部ok。实测配置为6CPU/10GiB、256MiB shm、restart=no、privileged=false，仅127.0.0.1:8929；三个专用命名卷，无宿主目录或socket挂载。

Docker Hub普通pull遭遇registry EOF。未更改Docker/DNS/代理设置，改用系统curl的进程级IPv4从同一官方仓库下载。arm64 manifest与此前记录的 `sha256:1d72e8769f7c0f417ac5f8a2e2ecff7ccaded3d75072873148ee6b4f384a5742` 一致；9层压缩blob、config和解压diff_id逐一SHA256核对，构建本地load归档并导入。导入image ID为 `sha256:9f4af13b2258dc29b6da03a03ddf78e9721f48add57a88a2a25b712d72065bb9`，再次核对linux/arm64后执行原compose的 `up -d --pull never`。没有替换版本或使用第三方镜像。

本次仅打开原已安装Docker Desktop；daemon 27.4.0，VM 14CPU/17.29GiB，无配置调整或daemon重启。两个已有Kubernetes容器保持running；旧项目路径不存在容器bind mount依赖。初始化结束时GitLab约2.97GiB内存，瞬时使用量不代表容量保证。

宿主机直接请求监控端点返回404，容器loopback请求返回200。保留默认监控IP allowlist，不为检查扩大权限；宿主机访问可用性使用登录页。详见GitLab官方健康检查说明：https://docs.gitlab.com/administration/monitoring/health_check/ 。

管理员初始密码文件仅验证存在性，没有读取、复制或输出密码。下一步由用户在本机终端按官方安装手册读取初始密码，在本机浏览器以root登录并修改密码；不要发送到聊天或日志。尚未创建项目、注册Runner、创建token、添加GitLab远端、推送、触发pipeline或部署业务。GitLab服务端CI Lint及真实Runner验收仍待接入。

迁移后的macOS完整测试为51 passed，离线CI配置与双产品smoke通过；此前Linux50项结果仍是历史证据，本次未重跑Linux测试。原始脱敏状态、资源及组件检查见initialization.json。
