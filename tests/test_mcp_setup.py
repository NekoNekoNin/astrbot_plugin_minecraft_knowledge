"""Exercise MCP lifecycle ownership and rollback without production mutations."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mcp_setup import PAUSED, SERVER, ManagedMCP


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "mcp.json"
    unrelated = {"url": "https://example.invalid/mcp", "active": True}
    path.write_text(json.dumps({"mcpServers": {"other": unrelated}}), encoding="utf-8")
    manager = SimpleNamespace(
        mcp_config_path=path,
        mcp_server_runtime_view={},
        func_list=[],
        enable_mcp_server=AsyncMock(),
        disable_mcp_server=AsyncMock(),
    )

    def save(value):
        path.write_text(json.dumps(value), encoding="utf-8")
        return True

    manager.save_mcp_config = save
    controller = ManagedMCP(
        manager, tmp_path / "path with spaces/server.py", tmp_path / "config.json"
    )
    return controller, manager, unrelated


@pytest.mark.asyncio
async def test_first_install_registers_and_preserves_other_servers(setup):
    controller, manager, unrelated = setup
    await controller.start()
    config = controller.read()["mcpServers"]
    assert config["other"] == unrelated
    assert config[SERVER]["args"] == [str(controller.script)]
    assert config[SERVER]["env"]["MC_KNOWLEDGE_CONFIG"] == str(controller.config)
    manager.enable_mcp_server.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_off_is_preserved_even_after_unload(setup):
    controller, manager, _ = setup
    await controller.start()
    config = controller.read()
    config["mcpServers"][SERVER]["active"] = False
    manager.save_mcp_config(config)
    manager.enable_mcp_server.reset_mock()
    await controller.stop()
    await controller.start()
    assert controller.read()["mcpServers"][SERVER]["active"] is False
    manager.enable_mcp_server.assert_not_awaited()


@pytest.mark.asyncio
async def test_plugin_pause_restores_on_reload_but_not_when_disabled(setup):
    controller, manager, _ = setup
    await controller.start()
    manager.mcp_server_runtime_view[SERVER] = object()
    await controller.stop()
    assert controller.read()["mcpServers"][SERVER][PAUSED] is True
    manager.disable_mcp_server.assert_awaited_once_with(SERVER, timeout=10)
    await controller.start(enabled=False)
    assert not controller.read()["mcpServers"][SERVER]["active"]
    await controller.start()
    assert controller.read()["mcpServers"][SERVER]["active"]
    assert PAUSED not in controller.read()["mcpServers"][SERVER]


@pytest.mark.asyncio
async def test_unrelated_same_name_is_never_replaced(setup):
    controller, manager, unrelated = setup
    config = controller.read()
    config["mcpServers"][SERVER] = unrelated
    manager.save_mcp_config(config)
    await controller.start()
    await controller.stop()
    assert controller.read() == config
    manager.enable_mcp_server.assert_not_awaited()
    manager.disable_mcp_server.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_json_is_preserved(setup):
    controller, manager, _ = setup
    Path(manager.mcp_config_path).write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError):
        await controller.start()
    assert Path(manager.mcp_config_path).read_text(encoding="utf-8") == "broken"


@pytest.mark.asyncio
async def test_failure_rolls_back_only_own_entry(setup):
    controller, manager, unrelated = setup

    async def fail(*args, **kwargs):
        config = controller.read()
        config["mcpServers"]["concurrent"] = {"command": "python"}
        manager.save_mcp_config(config)
        raise TimeoutError

    manager.enable_mcp_server.side_effect = fail
    with pytest.raises(TimeoutError):
        await controller.start()
    config = controller.read()["mcpServers"]
    assert config["other"] == unrelated
    assert "concurrent" in config
    assert SERVER not in config


@pytest.mark.asyncio
async def test_manual_mode_does_not_register_anything(setup):
    controller, manager, _ = setup
    before = controller.read()
    await controller.start(automatic=False)
    assert controller.read() == before
    manager.enable_mcp_server.assert_not_awaited()
