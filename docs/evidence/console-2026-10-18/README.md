# 只读统一门户验收

2026-10-18，用户确认后按Standard Lane实现，先只读统一概览，未增加业务写操作。用户进一步明确“暂不创建，先体验业务门户与GitLab链接”，因此未创建门户token，未复用推送凭据；GitLab区域未配置是预期状态。

- 源码commit：34253a628b0cae7679204cb31109c2645c2ec3f8。
- 真实[流水线#5](http://127.0.0.1:8929/root/data-process/-/pipelines/5)的core_test/build_wheel/installed_wheel均成功，JUnit67项Linux测试零失败，macOS本地68项通过。
- API下载制品逐项核对：wheel/requirements摘要、manifest和安装报告commit一致；新增console-smoke在wheel包外启动真实loopback HTTP页面，验证安全会话、静态资源与内置commit，未读取业务状态或GitLab凭据。
- 浏览器实际验证五个视图、状态筛选、20条分页、详情、空态、390px窄屏；合成数据目录前后文件摘要一致。仅使用新建的专用合成目录，不接入现有业务目录。
- 独立审查发现入口末级symlink覆盖、异常心跳影响总览两项P2，补复现测试并修复，复核清除；详见review.md。
- 保留现有GitLab/Runner资源与认证、三个既有容器和卷，不执行真实UCI、worker常驻变更、数据库迁移或生产部署。

pipeline-5保存真实测试/状态报告和摘要，wheel不重复纳入Git。后续文档commit是新的SHA，需额外验证其真实流水线与安装版本，不将本记录冒充最新HEAD结果。当前流程仍只推main，未声称实现普通feature/MR的合并前CI或自动CD。
