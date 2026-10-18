# 只读统一门户 Implementation Plan

> 执行采用当前会话逐项实现与独立审查，避免并行修改共享文件。

**Goal:** 本机只读统一门户，整合业务运行与GitLab交付摘要。
**Architecture:** 同源FastAPI页面，独立只读查询/固定GitLab适配器，静态资源与应用随同一SHA wheel交付。
**Tech Stack:** Python3.11、FastAPI、Uvicorn、Jinja2、SQLite只读、原生CSS/JS。

## 1 基线与接口测试

- [x] 在干净codex/read-only-console分支运行 `.venv/bin/python -m pytest -q`，确认既有51项。
- [x] 新建 tests/test_web_console.py，以合成Platform目录建立测试状态；测试无cookie时API401、仅GET、分页、目录快照不变、日志/路径过滤。首先运行该测试观察缺少web模块的失败。
- [x] pyproject.toml锁定新增依赖，`uv lock`、`uv sync --frozen --extra dev --group build --no-editable`。

## 2 只读查询和GitLab适配

- [x] 新建src/data_process/web_store.py：登记产品、mode=ro/query_only、limit<=50、固定字段、分页、受限质量/日志，缺库返回未配置，不创建目录。
- [x] 新建src/data_process/web_gitlab.py：固定127.0.0.1:8929项目1，GET短超时、不跟重定向，白名单JSON响应；未配置/出错均显式状态。使用本地HTTP stub/MockTransport验证，不使用现有写权限token。
- [x] 运行 `.venv/bin/python -m pytest tests/test_web_console.py -q`，按失败逐项实现。

## 3 Web与界面

- [x] 新建src/data_process/web.py：create_app(config, access_secret)、固定Host/Origin、引导会话、HttpOnly Strict cookie、安全头、只读API、固定页面与资源；dp-console启动限制loopback，入口文件0600，不输出秘密。
- [x] 新建src/data_process/web_assets/index.html、console.css、console.js：统一总览、产品选择、状态分页、详情、交付/审计、研发摘要和应用版本；所有动态文本用textContent，无外部CDN。
- [x] 在pyproject增加dp-console脚本；wheel构建验收包含模板资源，扩展tests/test_ci_delivery.py验证已安装包中的资源与接口。

## 4 体验与安全验证

- [x] 专用忽略目录生成合成演示，临时loopback进程启动门户，不动现有服务。
- [x] 浏览器实际验证入口、五个导航、过滤、分页、详情、错误/空态、窄屏；保存脱敏截图与摘要。
- [x] 请求级测试会话、跨站、Host、非GET、路径/符号链接、GitLab断连；数据home前后摘要一致。
- [x] 独立reviewer读取代码与脱敏测试证据，重要缺陷修复后重新验证。

## 5 提交与交付

- [ ] 更新docs/12-console-runbook.md、agent.md和脱敏证据；不提交token/入口文件/运行数据。
- [ ] 全回归与服务端CI Lint后commit，正常合并main，显式双远端push，核对真实三项job与精确SHA制品。
- [ ] 从该wheel安装到隔离体验环境验证页面可用；若需要实时GitLab身份，在完成可审查实现后请求最小只读token创建确认，不使用管理员PAT或扩大现有Runner权限。
