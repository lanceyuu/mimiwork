"""Notion's browser connection coexists with manually configured accounts."""

import pytest

from coworker.connectors.descriptors import (
    ValidationResult,
    configured_mcp_server,
    get_descriptor,
    mcp_connector_for_server,
)
from coworker.connectors.setup import connect_connector, connector_list, disconnect_connector
from coworker.connectors.tool_defs import approval_for_tool, tool_dicts
from coworker.mcp.config import delete_global_server, put_global_server, read_global
from coworker.secrets import SecretStore


@pytest.fixture
def secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path))
    return SecretStore(tmp_path / "secrets.json")


def _connect(secrets, name="my-notion", **config):
    put_global_server(
        name,
        {"url": "https://mcp.notion.com/mcp", "auth": "oauth", **config},
    )
    secrets.put(f"mcp-oauth:{name}", {"tokens": {"access_token": "test-token"}})


def _notion(secrets):
    return next(c for c in connector_list(secrets) if c["name"] == "notion")


def test_an_existing_notion_mcp_alias_counts_as_connected_without_a_token_profile(secrets):
    _connect(secrets)
    before = read_global()

    notion = _notion(secrets)

    assert notion["connected"] and notion["enabled"]
    assert notion["mode"] == "mcp"
    assert notion["mcp_server"] == "my-notion"
    assert "accounts" not in notion
    assert secrets.get("notion:default") is None
    assert read_global() == before
    assert all(t["name"].startswith("mcp__notion__") for t in notion["tools"])


def test_an_unfinished_notion_signin_remains_disconnected(secrets):
    put_global_server("notion", {"url": "https://mcp.notion.com/mcp", "auth": "oauth"})

    notion = _notion(secrets)

    assert not notion["connected"]
    assert notion["mcp"]
    assert notion["mcp_status"] == "needs_auth"


def test_disabling_a_notion_mcp_server_keeps_manual_accounts_available(secrets):
    _connect(secrets, enabled=False)
    secrets.put("notion:account:manual", {"access_token": "manual-token", "account": "Manual"})
    secrets.put("notion:default", {"default_account": "manual", "enabled": True})

    notion = _notion(secrets)

    assert notion["connected"] and notion["enabled"]
    assert notion["mode"] == ""
    assert notion["accounts"][0]["account_id"] == "manual"
    assert any(t["name"] == "notion_search" for t in notion["tools"])


def test_mcp_listing_preserves_a_legacy_manual_token_and_its_profile(secrets):
    _connect(secrets)
    profile = {"access_token": "manual-token", "account": "Manual", "enabled": True}
    secrets.put("notion:default", profile)

    assert _notion(secrets)["mode"] == "mcp"
    assert secrets.get("notion:default") == profile


def test_notion_mcp_disconnect_preserves_manual_accounts_and_server_restrictions(secrets):
    _connect(secrets, include_tools=["notion-search"], requires_approval=True)
    manual = {"access_token": "manual-token", "account": "Manual"}
    secrets.put("notion:account:manual", manual)
    secrets.put("notion:default", {"default_account": "manual", "mode": "mcp", "mcp_server": "my-notion"})

    assert disconnect_connector(secrets, "notion")["ok"]

    assert secrets.get("mcp-oauth:my-notion") is None
    assert secrets.get("notion:account:manual") == manual
    assert secrets.get("notion:default") == {"default_account": "manual"}
    assert read_global()["my-notion"]["enabled"] is False
    assert read_global()["my-notion"]["include_tools"] == ["notion-search"]
    assert read_global()["my-notion"]["requires_approval"] is True


def test_notion_connection_matching_requires_the_official_endpoint(secrets):
    assert mcp_connector_for_server("my-brain", "https://mcp.notion.com/mcp/") == "notion"
    assert mcp_connector_for_server("notion", "https://example.com/mcp") is None
    assert mcp_connector_for_server("notion", "https://mcp.notion.com.evil/mcp") is None
    assert mcp_connector_for_server("notion", 123) is None
    _connect(secrets, name="notion", enabled=False)
    _connect(secrets, name="connected-brain")
    assert configured_mcp_server("notion", secrets).name == "connected-brain"


def test_known_notion_reads_do_not_gate_and_changes_and_unknown_tools_do(secrets):
    _connect(secrets)
    tools = tool_dicts(secrets, "notion")
    assert any(t["name"] == "mcp__notion__notion-get-enabled-skills" for t in tools)
    for tool in tools:
        assert approval_for_tool(tool["name"]) is (tool["kind"] != "read")
    assert approval_for_tool("mcp__notion__new-vendor-tool") is True


def test_removing_notion_mcp_restores_preserved_manual_accounts(secrets):
    _connect(secrets)
    manual = {"access_token": "manual-token", "account": "Manual"}
    secrets.put("notion:account:manual", manual)
    secrets.put("notion:default", {"default_account": "manual", "mode": "mcp", "mcp_server": "my-notion"})

    delete_global_server("my-notion")
    notion = _notion(secrets)

    assert notion["connected"] and notion["enabled"]
    assert notion["mode"] == ""
    assert notion["accounts"][0]["account_id"] == "manual"
    assert any(t["name"] == "notion_search" for t in notion["tools"])
    assert secrets.get("notion:account:manual") == manual


def test_disabling_an_explicit_mcp_connection_keeps_it_disabled(secrets):
    _connect(secrets, enabled=False)
    secrets.put("notion:default", {"mode": "mcp", "mcp_server": "my-notion"})

    notion = _notion(secrets)

    assert notion["connected"]
    assert not notion["enabled"]
    assert notion["mode"] == "mcp"
    assert notion["mcp_status"] == "disabled"


def test_successful_manual_notion_connect_switches_modes_without_losing_browser_signins(secrets, monkeypatch):
    _connect(secrets, include_tools=["notion-search"], requires_approval=True)
    _connect(secrets, name="other-notion")
    secrets.put("notion:default", {"mode": "mcp", "mcp_server": "my-notion", "enabled": False})
    monkeypatch.setattr(get_descriptor("notion"), "validate", lambda _: ValidationResult(True, identity="Manual"))
    before = read_global()

    result = connect_connector(secrets, "notion", {"access_token": "manual-token"})

    assert result["ok"]
    notion = _notion(secrets)
    assert notion["connected"] and notion["enabled"]
    assert notion["mode"] == ""
    assert notion["accounts"][0]["account_id"] == "manual"
    assert any(t["name"] == "notion_search" for t in notion["tools"])
    assert "mode" not in secrets.get("notion:default")
    assert "mcp_server" not in secrets.get("notion:default")
    assert secrets.get("notion:account:manual")["access_token"] == "manual-token"
    assert read_global() == {name: {**config, "enabled": False} for name, config in before.items()}
    assert secrets.get("mcp-oauth:my-notion")["tokens"]["access_token"] == "test-token"
    assert secrets.get("mcp-oauth:other-notion")["tokens"]["access_token"] == "test-token"


def test_failed_manual_notion_validation_keeps_the_current_mcp_connection(secrets, monkeypatch):
    _connect(secrets)
    profile = {"mode": "mcp", "mcp_server": "my-notion"}
    secrets.put("notion:default", profile)
    monkeypatch.setattr(get_descriptor("notion"), "validate", lambda _: ValidationResult(False, error="Invalid token"))
    before = read_global()

    result = connect_connector(secrets, "notion", {"access_token": "invalid-token"})

    assert not result["ok"]
    assert read_global() == before
    assert secrets.get("notion:default") == profile
    assert secrets.get("notion:account:default") is None
    assert _notion(secrets)["mode"] == "mcp"
