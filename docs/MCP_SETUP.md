# 原生 MCP 接入

## 默认：自动接入

1. 安装完整插件包及 requirements.txt 的依赖，需要 AstrBot 4.29.1 或更高版本。
2. 打开插件卡片的“配置”，保持“启用资料查询”和“自动登记并连接 MCP”开启。
3. 插件自动使用当前 Python、实际安装位置及本插件配置文件，创建 `minecraft-knowledge` stdio 服务并连接五个工具。无需手工登记 MCP。
4. 管理员发送 `/mc资料状态`，检查连接状态和工具数量。使用工具白名单的人格，还需允许 `minecraft_search`、`minecraft_read`、`minecraft_related`、`minecraft_versions`、`minecraft_sources`。

MC百科与 Modrinth 无需密钥。CurseForge 官方 API Key 由用户自行申请，在原生插件配置中填写；留空只影响 CurseForge。插件不申请、不分发共用 Key，也不会虚构缺失数据。

## 开关与升级

- 在 MCP 管理中手动停用服务，插件会保留该选择；需要使用时在 MCP 管理中重新启用。
- 重载插件会暂停并重新连接自己的服务；禁用或卸载插件会暂停自身连接。其他 MCP 服务保持原有配置。
- 同名服务指向其他脚本时不覆盖，请先将冲突服务改名。
- MCP 配置文件损坏时不覆盖文件，请先修复 JSON；依赖缺失或启动失败会在状态命令中提示。
- 来源开关、超时、缓存和 Key 由后续工具调用读取；代码升级需重载插件。

## 高级：自行管理

关闭“自动登记并连接 MCP”后，可在 MCP 管理自行维护该服务。保存配置会重载插件并暂停已有连接，随后可在 MCP 管理中重新启用。关闭资料查询总开关或禁用插件仍会停止本插件的连接。

服务命令为安装依赖的 Python 解释器，参数仅包含本插件 `server.py` 的绝对路径，环境变量 `MC_KNOWLEDGE_CONFIG` 指向 AstrBot 数据目录下的 `config/astrbot_plugin_minecraft_knowledge_config.json`。手动配置时无需把 CurseForge Key 写入 MCP 环境变量。
