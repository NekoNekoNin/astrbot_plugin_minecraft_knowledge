# 原生插件配置

入口：AstrBot → 插件 → **Minecraft资料助手** → **配置**。普通设置无需独立 Web 页面。

保存会重载插件，请先等待正在处理的请求结束。

| 配置键 | 界面名称 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enabled` | 基础 · 启用资料查询 | true | 关闭后停止检索指导与本插件 MCP 连接；不会改变其他 MCP 服务。 |
| `auto_connect_mcp` | 基础 · 自动登记并连接 MCP | true | 默认自动提供五个资料工具，无需手填命令和路径。保留 MCP 管理中手动停用的状态；关闭本项后交由 MCP 管理操作。 |
| `attach_guidance` | 基础 · 相关话题自动检索指导 | true | 仅匹配当前消息中的 Minecraft、模组或三站相关词；普通聊天不添加指导。 |
| `mcmod_enabled` | 资料来源 · MC百科 | true | 控制模组、物品、机制与教程的搜索及正文读取。 |
| `modrinth_enabled` | 资料来源 · Modrinth | true | 控制项目介绍、平台下载量与版本文件查询，不需要 API Key。 |
| `curseforge_enabled` | 资料来源 · CurseForge | true | 需要自己的 API Key；仅启用此开关不会自动获得密钥或访问权限。 |
| `curseforge_api_key` | CurseForge · API Key | "" | 需要用户自行向 CurseForge 申请。仅在本机配置保存，默认隐藏；留空时 MC百科与 Modrinth 仍可使用，密钥修改后由后续查询读取。 |
| `request_timeout_seconds` | 高级 · 来源请求超时（秒） | 18 | 5–60 秒。适用于后续查询，来源故障时返回明确错误。 |
| `cache_ttl_seconds` | 高级 · 来源缓存（秒） | 300 | 0–3600 秒；0 关闭后续缓存命中。结果仍保留实际获取时间。 |
