<img src="logo.png" width="80" height="80" alt="Minecraft资料助手图标">

# Minecraft资料助手

查阅 MC百科、Modrinth 和 CurseForge 的模组资料、教程与版本；CurseForge 需自备 API Key。

版本：`1.2.0` · 许可：[MIT](LICENSE)

作者：**NekoNekoNin**。

## 能做什么

- 读取 MC百科模组、物品/机制和教程正文，支持长文续读与相关资料目录。
- 查询 Modrinth 与 CurseForge 的项目介绍、平台下载量、版本文件和加载器信息。
- 通过原生 MCP 提供 5 个查询工具，来源开关、密钥和网络参数在插件配置中管理。

## 支持平台与标签

支持 QQ / OneBot v11（`aiocqhttp`，如 NapCat）与 AstrBot 内置 WebChat（`webchat`）。市场平台字段表示消息适配器；当前声明按已接入和验收范围填写，其他平台尚未验收。

标签：Minecraft、MC百科、模组、教程、MCP。

## 安装

在 AstrBot 的插件管理上传本插件发布 ZIP，或使用[本仓库地址](https://github.com/NekoNekoNin/astrbot_plugin_minecraft_knowledge)安装。内部插件名保持 `astrbot_plugin_minecraft_knowledge`，升级时沿用已有配置。元数据已绑定本仓库，更新时请核对版本与更新记录。

默认自动登记并连接本插件的 stdio MCP 服务，无需填写 Python 或脚本路径。MC百科和 Modrinth 不需要密钥；CurseForge 官方 API 需要自己的 API Key，未配置时不会虚构下载量。

## 设置

入口：**AstrBot → 插件 → Minecraft资料助手 → 配置**。常用选项直接显示，适用时提供中文下拉标签、数值滑块、条件显示与高级折叠。完整选项见 [配置说明](docs/CONFIGURATION.md)。

## 聊天示例

- “查机械动力的 MC百科介绍和入门教程。”
- “读取这篇模组教程，说明前置条件和步骤。”
- “查看 Sodium 指定 Minecraft 版本与加载器的发布文件。”

## 使用边界

各平台下载量独立统计，不相加。项目支持的版本汇总不能证明某一文件兼容，安装判断应核对同一文件的 game_versions 与 loaders。仅返回资料与下载链接，不下载或执行模组。

## MCP 接入

详见 [MCP 接入说明](docs/MCP_SETUP.md)。自动管理的服务名称为 `minecraft-knowledge`，配置文件路径只指向本插件配置。保留 MCP 管理中手动停用的开关；插件重载会重新连接，禁用插件会停止自身连接。管理员可发送 `/mc资料状态` 检查连接与工具数量。使用工具白名单的人格仍需允许这五个工具。

## 开发与检查

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
```

涉及实际 AstrBot 注册器的测试需提供框架源码路径 `ASTRBOT_SOURCE`；未提供时相关集成项明确跳过，不把跳过当作完整集成验收。联网与真实聊天验收另行执行。

封面使用相关原有图片素材，来源与权利说明见 [素材说明](docs/ASSETS.md)。

2026-10-26 已在 AstrBot 4.29.1 桌面版实际打开插件卡片和原生配置弹窗验收；普通设置无需独立网页。此验收不等同于重新测试全部聊天功能。
