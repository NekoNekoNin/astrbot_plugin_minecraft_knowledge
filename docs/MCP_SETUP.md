# 原生 MCP 接入

1. 安装完整插件包和 requirements.txt 的依赖。
2. 在插件“配置”中启用所需来源，按需填写 CurseForge API Key。
3. 在 AstrBot 的 MCP 管理创建 stdio 服务。Python 应指向装有依赖的解释器，脚本应指向本插件 server.py，配置路径指向本插件的配置 JSON。以下路径均为示例，替换为实际位置。

```json
{
  "mcpServers": {
    "minecraft-knowledge": {
      "active": true,
      "command": "/path/to/python",
      "args": ["/path/to/astrbot/data/plugins/astrbot_plugin_minecraft_knowledge/server.py"],
      "env": {
        "MC_KNOWLEDGE_CONFIG": "/path/to/astrbot/data/config/astrbot_plugin_minecraft_knowledge_config.json"
      }
    }
  }
}
```

Windows 可使用正斜线绝对路径。首次登记后重启该 MCP 服务，检查 minecraft_search/read/related/versions/sources 五个工具已激活。来源开关、超时、缓存和密钥会在后续查询读取；升级服务代码后需重启 MCP 进程。使用工具白名单的人格还需允许这五个工具。
