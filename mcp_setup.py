"""Manage only this plugin's local MCP registration through AstrBot APIs."""

import copy
import json
import os
import sys
from pathlib import Path

SERVER = "minecraft-knowledge"
OWNER = "astrbot_plugin_minecraft_knowledge"
PAUSED = "_plugin_paused"


class ManagedMCP:
    """Preserve manual switches and unrelated servers during plugin reloads."""

    def __init__(self, manager, script: Path, config: Path):
        self.manager = manager
        self.script = script.resolve()
        self.config = config.resolve()
        self.message = "尚未初始化"

    def read(self):
        """Read strictly so invalid user configuration is never overwritten."""
        path = Path(self.manager.mcp_config_path)
        result = (
            json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        )
        if not isinstance(result, dict) or not isinstance(
            result.get("mcpServers", {}), dict
        ):
            raise ValueError("Invalid MCP configuration")
        result.setdefault("mcpServers", {})
        return result

    def owns(self, entry):
        """Require the exact script path before changing an existing entry."""
        return (
            isinstance(entry, dict)
            and isinstance(entry.get("args"), list)
            and any(
                isinstance(arg, str) and Path(arg).resolve() == self.script
                for arg in entry["args"]
            )
            and "url" not in entry
        )

    def status(self):
        """Return operational state without environment variables or secrets."""
        return {
            "server": SERVER,
            "connected": SERVER in self.manager.mcp_server_runtime_view,
            "tool_count": sum(
                getattr(tool, "mcp_server_name", None) == SERVER
                for tool in self.manager.func_list
            ),
            "message": self.message,
        }

    async def start(self, enabled=True, automatic=True):
        """Register and connect the owned service, preserving explicit manual off."""
        if not enabled:
            await self.stop()
            self.message = "插件资料查询已关闭"
            return
        if not automatic:
            self.message = "自动连接已关闭，请在 MCP 管理中管理服务"
            return
        configuration = self.read()
        entries = configuration["mcpServers"]
        previous = entries.get(SERVER)
        if previous is not None and not self.owns(previous):
            self.message = "同名 MCP 服务属于其他配置，请先在 MCP 管理中改名"
            return
        if previous and previous.get("active") is False and not previous.get(PAUSED):
            self.message = "MCP 已被手动停用，保留当前开关；可在 MCP 管理中启用"
            return
        entry = copy.deepcopy(previous or {})
        environment = dict(entry.get("env") or {})
        environment["MC_KNOWLEDGE_CONFIG"] = str(self.config)
        # Desktop Python loads dependencies from a separate site-packages directory.
        inherited = os.environ.get("PYTHONPATH", "")
        if "PYTHONPATH" not in environment:
            search_paths = [
                str(Path(path).resolve())
                for path in sys.path
                if path
                and Path(path).is_dir()
                and Path(path).name in {"site-packages", "dist-packages"}
            ]
            if inherited:
                search_paths.extend(inherited.split(os.pathsep))
            if search_paths:
                environment["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(search_paths))
        entry.update(
            command=sys.executable,
            args=[str(self.script)],
            env=environment,
            active=True,
        )
        entry["_plugin_owner"] = OWNER
        entry.pop(PAUSED, None)
        entries[SERVER] = entry
        changed = entry != previous
        if changed and not self.manager.save_mcp_config(configuration):
            raise OSError("Could not save MCP registration")
        try:
            if changed and SERVER in self.manager.mcp_server_runtime_view:
                await self.manager.disable_mcp_server(SERVER, timeout=10)
            await self.manager.enable_mcp_server(SERVER, entry, timeout=30)
            self.message = "MCP 已连接，可使用五个资料工具"
        except BaseException:
            if changed:
                latest = self.read()
                if latest["mcpServers"].get(SERVER) == entry:
                    if previous is None:
                        latest["mcpServers"].pop(SERVER, None)
                    else:
                        latest["mcpServers"][SERVER] = previous
                    self.manager.save_mcp_config(latest)
            raise

    async def stop(self):
        """Pause only our own registration so disabled plugins stay disconnected."""
        configuration = self.read()
        entry = configuration["mcpServers"].get(SERVER)
        if not self.owns(entry):
            return
        if entry.get("active", True):
            entry.update(active=False, **{PAUSED: True})
            if not self.manager.save_mcp_config(configuration):
                raise OSError("Could not pause MCP registration")
        if SERVER in self.manager.mcp_server_runtime_view:
            await self.manager.disable_mcp_server(SERVER, timeout=10)
        self.message = "插件 MCP 已暂停"
