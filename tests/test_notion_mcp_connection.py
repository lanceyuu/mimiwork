"""Notion browser connection reuses the user's MCP configuration."""

from types import SimpleNamespace

import pytest

from coworker.mcp.config import put_global_server, read_global
from coworker.server.manager import SessionManager


@pytest.mark.asyncio
async def test_notion_browser_connect_loads_the_full_server_catalog(tmp_path, monkeypatch):
    manager = SessionManager(data_dir=tmp_path / "data")
    seen = []

    async def connect(name):
        seen.append(name)
        return {"ok": True, "tools": 24}

    monkeypatch.setattr(manager, "connect_mcp", connect)
    assert (await manager.mcp_connect_connector("notion"))["ok"]
    assert seen == ["notion"]
    raw = read_global()["notion"]
    assert raw["url"] == "https://mcp.notion.com/mcp"
    assert raw["auth"] == "oauth"
    assert raw["requires_approval"] is False
    assert "include_tools" not in raw
    assert manager.secrets.get("notion:default")["mcp_server"] == "notion"


@pytest.mark.asyncio
async def test_notion_reconnect_reuses_an_alias_and_keeps_tool_restrictions(tmp_path, monkeypatch):
    manager = SessionManager(data_dir=tmp_path / "data")
    config = {
        "url": "https://mcp.notion.com/mcp",
        "auth": "oauth",
        "enabled": False,
        "include_tools": ["notion-search", "notion-fetch"],
        "exclude_tools": ["notion-update-page"],
        "requires_approval": True,
    }
    put_global_server("my-notion", config)
    manager.secrets.put("notion:default", {"default_account": "manual-workspace"})
    seen = []

    async def connect(name):
        seen.append(name)
        return {"ok": True, "tools": 2}

    monkeypatch.setattr(manager, "connect_mcp", connect)
    assert (await manager.mcp_connect_connector("notion"))["ok"]
    assert seen == ["my-notion"]
    assert read_global() == {"my-notion": {**config, "enabled": True}}
    profile = manager.secrets.get("notion:default")
    assert profile["default_account"] == "manual-workspace"
    assert profile["mcp_server"] == "my-notion"


@pytest.mark.asyncio
async def test_failed_notion_reconnect_preserves_existing_config_and_shows_the_error(tmp_path, monkeypatch):
    manager = SessionManager(data_dir=tmp_path / "data")
    config = {
        "url": "https://mcp.notion.com/mcp",
        "auth": "oauth",
        "enabled": False,
        "exclude_tools": ["notion-update-page"],
    }
    put_global_server("work-notion", config)

    async def connect(name):
        return {"ok": False, "error": "Sign-in cancelled"}

    monkeypatch.setattr(manager, "connect_mcp", connect)
    assert not (await manager.mcp_connect_connector("notion"))["ok"]
    assert read_global() == {"work-notion": config}
    row = next(c for c in manager.list_connectors() if c["name"] == "notion")
    assert row["mcp_error"] == "Sign-in cancelled"
    assert manager.secrets.get("notion:default") is None


@pytest.mark.asyncio
async def test_failed_first_notion_sign_in_stays_available_for_retry(tmp_path, monkeypatch):
    manager = SessionManager(data_dir=tmp_path / "data")

    async def connect(name):
        return {"ok": False, "error": "Sign-in timed out"}

    monkeypatch.setattr(manager, "connect_mcp", connect)
    assert not (await manager.mcp_connect_connector("notion"))["ok"]
    row = next(c for c in manager.list_connectors() if c["name"] == "notion")
    assert row["mcp_status"] == "needs_auth"
    assert row["mcp_error"] == "Sign-in timed out"
    assert read_global()["notion"]["auth"] == "oauth"


@pytest.mark.asyncio
async def test_notion_connect_preserves_an_unrelated_server_with_the_same_name(tmp_path):
    manager = SessionManager(data_dir=tmp_path / "data")
    config = {"command": "custom-notion-server", "args": ["--local"]}
    put_global_server("notion", config)
    assert not (await manager.mcp_connect_connector("notion"))["ok"]
    assert read_global() == {"notion": config}


def test_existing_notion_mcp_status_and_controls_remain_visible(tmp_path):
    manager = SessionManager(data_dir=tmp_path / "data")
    put_global_server("notion", {"url": "https://mcp.notion.com/mcp", "auth": "oauth"})
    manager.secrets.put("mcp-oauth:notion", {"tokens": {"access_token": "test-token"}})
    manager._mcp_authorizing.add("notion")
    row = next(c for c in manager.list_connectors() if c["name"] == "notion")
    assert row["mcp_status"] == "authorizing"
    assert manager.list_mcp()[0]["status"] == "authorizing"
    manager._mcp_authorizing.clear()
    manager.mcp._conns["notion"] = SimpleNamespace(tools=[])
    assert manager.list_mcp()[0]["status"] == "connected"
    manager.patch_mcp("notion", {"enabled": False})
    assert manager.list_mcp()[0]["status"] == "disabled"
