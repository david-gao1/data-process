# 本机只读统一门户运行手册

首版提供统一总览、数据运行/详情、正式交付/审计、GitLab交付摘要与实际应用版本。仅本机127.0.0.1，默认端口8930；业务访问只读，不触发worker、定时任务、业务发布或回滚。独立进程临时运行，不注册launchd、不改Docker或既有服务。

## 启动与本机安全入口

安装经过验证的wheel及其runtime-requirements后，使用包内 `dp-console`：

```bash
dp-console --config /绝对路径/console-config.json --entry /绝对路径/私有目录/entry.html
```

配置示例（路径必须由操作者登记，不通过浏览器提交）：

```json
{
  "products": {
    "daily_active": {"label": "三省活跃用户 · 合成演示", "home": "/绝对路径/专用演示/daily_active"},
    "retail_daily": {"label": "零售日汇总 · 合成演示", "home": "/绝对路径/专用演示/retail_daily"}
  }
}
```

在本机浏览器打开生成的入口HTML；启动器只输出提示，不输出引导秘密。入口为0600、父目录应为当前用户0700，必须在Git忽略目录中。浏览器通过fragment将进程内引导值带到本机页面，页面立即移除fragment，再以同源JSON兑换HttpOnly/SameSite=Strict会话cookie。入口单次使用，进程重启后旧会话失效；同浏览器会话内可直接刷新 http://127.0.0.1:8930/ 。不要复制引导值到聊天、命令、截图或远端URL；不要在编辑器预览入口HTML源码。

端口冲突时可使用8930–8999内的另一个端口并重新生成入口。固定Host校验与端口匹配，localhost或局域网地址不会自动开放。停止使用前台Ctrl-C，或仅终止明确识别的门户进程；不要重启Docker/GitLab/worker。

仓库内开发可用 `.venv/bin/dp-console --config .local/console/config.json --entry .local/console/entry.html`。开发版缺包内构建身份时显示未知，不把Git HEAD或GitLab main误作已安装版本。真实交付应从指定SHA的wheel启动，以页面内置完整commit核对。

## GitLab只读接入

未配置时页面显示“未配置”，仍可使用固定本机项目链接；不可用时清空当前流水线摘要并显示不可用，不显示上次成功冒充当前状态。创建专用只读身份需要本次明确授权：read_api、项目root/data-process、满足查询的最低角色、有限期限，不能从本手册推断永久批准。

获准后，把token保存到0600本地文件（例如 `.local/console/gitlab-readonly.json`），结构仅有 `token` 字段；禁止打印内容。服务器配置增加 `gitlab_token_file` 的绝对路径，重启门户并打开新入口。不要复用api/write_repository推送凭据；浏览器不持有GitLab token。适配器只请求固定127.0.0.1:8929项目1的GET接口、不跟重定向、不转发浏览器URL，短超时并限制响应大小与字段。

页面分别显示main完整SHA、最近main流水线、当前安装SHA对应流水线。应用旧版本与main不一致是需要展示的事实，不能把最新main成功当作旧安装版本已验收。

## 数据与故障边界

SQLite使用mode=ro/query_only；产品缺库显示未配置，不自动建库，损坏心跳隔离到该产品。运行与交付/审计每页最多50条（页面20），按已登记产品与run查询；不提供任意路径、SQL、原始CSV/Parquet或数据库下载。

日志仅返回允许的状态行，其他文本不显示；质量摘要需与数据库report_hash和业务日期匹配。缺失、符号链接逃逸或过大文件返回无可用摘要，不展示原始错误/私有路径/凭据。前端动态内容使用textContent；无外部CDN、字体或脚本。

失败时先区分访问会话、产品未配置、业务worker未活跃、GitLab连接和应用版本。worker在演示任务结束后停止可显示未活跃，不代表门户故障。排队演示任务仅用于列表验证，门户不会自动执行它们。

## 验证与交付

本地测试覆盖会话/Host/跨站、输入大小、符号链接、异常心跳、只读目录快照、分页/空态、GitLab断连和精确SHA。浏览器验证五个导航、筛选、分页、详情与窄屏，确认数据文件摘要前后不变。installed_wheel作业增加包外真实HTTP console-smoke，产出 .ci-reports/console-smoke.json；它只使用临时空产品配置、loopback与进程内凭据，无真实业务状态/GitLab凭据。

测试浏览器使用的会话与用户浏览器不同，完成自动测试后若要给用户打开入口，需要重启门户生成新的单次入口。提交不包含配置、入口、令牌或运行数据，main按当次授权同步两远端，并逐一核对该精确SHA的真实流水线和制品。
