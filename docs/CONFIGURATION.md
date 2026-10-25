# 原生插件配置

入口：AstrBot → 插件 → **NekoNekoNin · Minecraft资料助手** → **配置**。本版不新增独立 Web 设置页。

以 AstrBot 4.29.1 的原生配置组件核对下拉标签、滑块、条件显示与高级折叠。配置键保持兼容；保存会重载插件，正在处理的请求应先完成。

| 配置键 | 界面名称 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enabled` | 基础 · 启用资料查询 | true | 关闭后停止注入指导，MCP 服务也将停止查询；MCP 连接可在工具管理中独立停用。 |
| `attach_guidance` | 基础 · 相关话题自动检索指导 | true | 仅匹配当前消息中的 Minecraft、模组或三站相关词；普通聊天不添加指导。 |
| `mcmod_enabled` | 资料来源 · MC百科 | true | 控制模组、物品、机制与教程的搜索及正文读取。 |
| `modrinth_enabled` | 资料来源 · Modrinth | true | 控制项目介绍、平台下载量与版本文件查询，不需要 API Key。 |
| `curseforge_enabled` | 资料来源 · CurseForge | true | 需要自己的 API Key；仅启用此开关不会自动获得密钥或访问权限。 |
| `curseforge_api_key` | CurseForge · API Key | （留空） | 仅在本机配置保存，界面默认隐藏；留空时 MC百科与 Modrinth 正常使用。请先在 MCP 管理登记服务，密钥变更由服务后续查询读取。 |
| `request_timeout_seconds` | 高级 · 来源请求超时（秒） | 18 | 5–60 秒。适用于后续查询，来源故障时返回明确错误。 |
| `cache_ttl_seconds` | 高级 · 来源缓存（秒） | 300 | 0–3600 秒；0 关闭后续缓存命中。结果仍保留实际获取时间。 |
