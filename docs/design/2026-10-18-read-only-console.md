# 只读统一门户设计

Standard Lane。用户在2026-10-18确认 docs/11-devops-visual-console-roadmap.md 的首版方向与 FastAPI 同源方案；本规格将该范围落实为可验证接口，不增加业务写操作或宿主部署权限。

## 功能与边界

本机127.0.0.1:8930，合成演示为默认体验，产品由服务端配置映射到登记的目录。导航：总览、数据运行、正式交付、研发交付、应用版本。运行列表分页与状态筛选，详情只显示结构化状态、质量摘要和受限/转义日志。GitLab端固定项目 root/data-process，后台只允许GET分支/pipeline/jobs接口；不触发任务，不接收客户端URL/路径/SQL。未配置只读凭据则明确显示未连接。

运行、交付、审计从SQLite mode=ro / query_only读取；不迁移schema、不调用init/monitor/check、不读原始数据、CSV或Parquet内容。通过已登记run查质量摘要和日志，拒绝符号链接逃逸；限制读取大小与返回字段，日志只显示受控状态行，不回显任意业务文本。应用版本从包内_build_info读取，开发源码显示开发版本/未知，不用移动main冒充已安装版本。

## 访问与凭据

门户启动时产生进程内随机访问口令，不输出口令；启动器在仅当前用户可读的0600本地文件保存入口HTML（fragment携带一次性引导值，URL查询参数和HTTP日志不含秘密）。浏览器脚本用同源POST /session兑换HttpOnly、SameSite=Strict cookie，随后删除fragment；后端校验Host、Origin、Fetch-Metadata，拒绝跨站访问；只允许固定本机端口。会话是进程内签发/校验，重启失效，不创建账号库。其余所有API只读，非GET/HEAD拒绝。

新GitLab只读项目token的创建/持久化须独立确认；实现和模拟测试先完成，门户不得读取现有写权限bot文件。配置方式只接受服务端受限文件，read_api+最低可用项目角色，固定127.0.0.1:8929目标；拒绝重定向，短超时，响应白名单，不返回token/原始错误/任意URL。断连显示不可用，不假装成功。新token获批后再接入真数据。

## 结构和交付

web_store.py负责分页只读查询；web_gitlab.py负责固定目标只读HTTP；web.py负责路由/会话/安全头/启动；web_assets包含模板CSS/JS，随Python wheel打包。FastAPI/Uvicorn锁定依赖；页面采用无构建静态壳与同源API，不引入未使用的模板运行依赖；httpx用于TestClient测试。CLI和worker不改业务规则。

视觉采用深墨色导航、米白工作区、青绿色运行状态与橙色故障提示；版本与完整SHA可展开，状态有文字，适配移动屏。无外部CDN/字体请求，无浏览器GitLab token。

验收：只读数据库与目录快照不变；分页/空态/缺失/坏数据/越权路径/转义/跨站/Host/会话测试；GitLab不可用与精确SHA映射测试；浏览器筛选、详情、刷新、窄屏；完整回归、CI、wheel外部安装并启动真实页面。独立安全审查后合并main，两远端SHA核对。新GitLab身份未获准时交付可运行门户和明确未连接状态，不扩权。
