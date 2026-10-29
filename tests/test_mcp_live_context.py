"""MCP availability follows the next turn without replacing the conversation."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from helpers import CapturingProvider

from coworker.automation.models import Schedule, ScheduledTask
from coworker.mcp.client import MCPManager
from coworker.mcp.config import MCPServerDef, put_global_server
from coworker.server.manager import SessionManager


def _tool(name):
    return SimpleNamespace(
        name=name, description="Read a page",
        inputSchema={"type": "object", "properties": {}},
    )


async def test_an_open_chat_loads_added_servers_and_removes_disabled_tools(tmp_path, monkeypatch):
    provider = CapturingProvider()
    manager = SessionManager(workspace=tmp_path, data_dir=tmp_path / "data", provider=provider)
    engine = manager.get_engine("chat", agent="chat")
    permissions = engine.permissions
    messages = engine.messages
    await manager.deliver_to_session("chat", "hello")

    manager.add_mcp("notes", {"url": "https://example.test/mcp"})

    async def ensure(server, *, interactive=False):
        assert interactive is False
        return SimpleNamespace(tools=[_tool("read_page")])

    monkeypatch.setattr(manager.mcp, "ensure", ensure)
    await manager.deliver_to_session("chat", "read my notes")
    assert manager.get_engine("chat") is engine
    assert engine.messages is messages
    assert engine.permissions is permissions
    assert "mcp__notes__read_page" in engine.registry.names()
    assert any('"notes": available, 1 tools.' in str(call) for call in provider.calls)
    assert "separate token connector can be disconnected" in engine.context_provider()

    manager.patch_mcp("notes", {"enabled": False})
    await manager.deliver_to_session("chat", "what is available?")
    assert "mcp__notes__read_page" not in engine.registry.names()
    assert any('"notes": disabled.' in str(call) for call in provider.calls)
    assert "load_skill" in engine.registry.names()
    manager.delete_mcp("notes")
    await manager.deliver_to_session("chat", "check again")
    assert "No MCP servers are configured" in engine.mcp_context
    assert "read my notes" in [m.get("content") for m in messages]


@pytest.mark.parametrize("entry", ["run", "retry", "resume", "scheduled"])
async def test_mcp_refresh_precedes_every_engine_entry_path(tmp_path, monkeypatch, entry):
    provider = CapturingProvider()
    manager = SessionManager(workspace=tmp_path, data_dir=tmp_path / "data", provider=provider)
    put_global_server("notes", {"url": "https://example.test/mcp"})
    if entry == "scheduled":
        task = ScheduledTask(
            title="Notes", instructions="Read my notes", workspace=str(tmp_path),
            schedule=Schedule(kind="cron", cron="0 9 * * *"), agent="chat",
        )
        engine = manager._build_task_engine(task, session_id="chat")
        manager._engines["chat"] = engine
    else:
        engine = manager.get_engine("chat", agent="chat")

    async def ensure(server, *, interactive=False):
        assert interactive is False
        return SimpleNamespace(tools=[_tool("read_page")])

    monkeypatch.setattr(manager.mcp, "ensure", ensure)
    if entry == "retry":
        engine.messages.extend([
            {"role": "user", "content": "Read my notes"},
            {"role": "notice", "kind": "error"},
        ])
        events = engine.retry()
    elif entry == "resume":
        engine.messages.extend([
            {"role": "user", "content": "Read my notes"},
            {"role": "assistant", "tool_calls": [{
                "id": "read-1", "type": "function",
                "function": {"name": "mcp__notes__read_page", "arguments": "{}"},
            }]},
        ])

        async def handle_pending(pending):
            assert engine.registry.get(pending[0].name) is not None
            for event in []:
                yield event

        monkeypatch.setattr(engine, "_handle_tool_calls", handle_pending)
        events = engine.resume()
    else:
        events = engine.run("Read my notes")
    _ = [event async for event in events]
    assert engine.registry.get("mcp__notes__read_page") is not None
    assert '"notes": available' in engine.mcp_context
    assert provider.calls


async def test_unavailable_servers_are_explained_without_exposing_credentials(tmp_path, monkeypatch):
    manager = SessionManager(workspace=tmp_path, data_dir=tmp_path / "data", provider=CapturingProvider())
    engine = manager.get_engine("chat", agent="chat")
    put_global_server("signed-out", {
        "url": "https://example.test/mcp", "auth": "oauth",
        "headers": {"Authorization": "Bearer secret-value"},
    })
    put_global_server("offline", {"url": "https://offline.test/mcp"})
    seen = []

    async def ensure(server, *, interactive=False):
        seen.append(server.name)
        assert interactive is False
        raise RuntimeError("secret-value")

    monkeypatch.setattr(manager.mcp, "ensure", ensure)
    _ = [event async for event in engine.run("What can you use?")]
    assert seen == ["offline"]
    assert '"signed-out": sign-in required' in engine.mcp_context
    assert '"offline": connection failed' in engine.mcp_context
    assert "secret-value" not in engine.mcp_context
    assert "https://" not in engine.mcp_context


async def test_notion_alias_keeps_custom_tools_and_user_approval_policy(tmp_path, monkeypatch):
    manager = SessionManager(workspace=tmp_path, data_dir=tmp_path / "data", provider=CapturingProvider())
    engine = manager.get_engine("chat", agent="chat")
    put_global_server("my-notion", {
        "url": "https://mcp.notion.com/mcp", "auth": "oauth",
        "requires_approval": False, "exclude_tools": ["notion-excluded"],
    })
    manager.secrets.put("mcp-oauth:my-notion", {"tokens": {"access_token": "secret"}})
    monkeypatch.setattr(manager, "effective_connectors", lambda *args: {"notion"})

    async def ensure(server, *, interactive=False):
        return SimpleNamespace(tools=[
            _tool("notion-search"), _tool("notion-custom"), _tool("notion-excluded"),
        ])

    monkeypatch.setattr(manager.mcp, "ensure", ensure)
    _ = [event async for event in engine.run("Read Notion")]
    assert engine.registry.get("mcp__my-notion__notion-search").metadata.requires_approval is False
    assert engine.registry.get("mcp__my-notion__notion-custom").metadata.requires_approval is True
    assert engine.registry.get("mcp__my-notion__notion-excluded") is None
    manager.patch_mcp("my-notion", {"requires_approval": True})
    _ = [event async for event in engine.run("Read Notion again")]
    assert engine.registry.get("mcp__my-notion__notion-search").metadata.requires_approval is True
    monkeypatch.setattr(manager, "effective_connectors", lambda *args: set())
    _ = [event async for event in engine.run("Check connections")]
    assert engine.registry.get("mcp__my-notion__notion-custom") is None
    assert "disabled for this conversation" in engine.mcp_context


@pytest.mark.parametrize("location", ["global", "workspace"])
async def test_notion_mcp_obeys_global_persona_and_session_switches(tmp_path, monkeypatch, location):
    manager = SessionManager(workspace=tmp_path, data_dir=tmp_path / "data", provider=CapturingProvider())
    engine = manager.get_engine("chat")
    config = {"url": "https://mcp.notion.com/mcp", "auth": "oauth"}
    if location == "global":
        put_global_server("my-notion", config)
    else:
        folder = tmp_path / ".coworker"
        folder.mkdir(exist_ok=True)
        (folder / "mcp.json").write_text(json.dumps({"mcpServers": {"my-notion": config}}))
        manager.workspace_trust.set_trusted(tmp_path, True)
    manager.secrets.put("mcp-oauth:my-notion", {"tokens": {"access_token": "secret"}})

    async def ensure(server, *, interactive=False):
        return SimpleNamespace(tools=[_tool("notion-search")])

    monkeypatch.setattr(manager.mcp, "ensure", ensure)
    await engine.prepare_turn()
    assert engine.registry.get("mcp__my-notion__notion-search") is not None
    manager.secrets.put("notion:default", {"enabled": False})
    await engine.prepare_turn()
    assert engine.registry.get("mcp__my-notion__notion-search") is None
    manager.secrets.put("notion:default", {"enabled": True})
    manager.persona_connections.set(engine.agent_name, "notion", False)
    await engine.prepare_turn()
    assert engine.registry.get("mcp__my-notion__notion-search") is None
    manager.session_connections.set("chat", "notion", True)
    await engine.prepare_turn()
    assert engine.registry.get("mcp__my-notion__notion-search") is not None
    manager.session_connections.set("chat", "notion", False)
    await engine.prepare_turn()
    assert engine.registry.get("mcp__my-notion__notion-search") is None


async def test_a_server_waiting_for_browser_sign_in_does_not_block_other_tools(tmp_path, monkeypatch):
    manager = SessionManager(workspace=tmp_path, data_dir=tmp_path / "data", provider=CapturingProvider())
    engine = manager.get_engine("chat")
    put_global_server("signing-in", {"url": "https://one.test/mcp", "auth": "oauth"})
    put_global_server("notes", {"url": "https://two.test/mcp"})
    manager._mcp_authorizing.add("signing-in")

    async def ensure(server, *, interactive=False):
        assert server.name == "notes"
        return SimpleNamespace(tools=[_tool("read_page")])

    monkeypatch.setattr(manager.mcp, "ensure", ensure)
    await asyncio.wait_for(engine.prepare_turn(), 1)
    assert engine.registry.get("mcp__notes__read_page") is not None
    assert "sign-in in progress" in engine.mcp_context


async def test_a_hung_connection_times_out_and_the_turn_keeps_other_tools(tmp_path, monkeypatch):
    from coworker.server import manager as manager_module

    manager = SessionManager(workspace=tmp_path, data_dir=tmp_path / "data", provider=CapturingProvider())
    engine = manager.get_engine("chat")
    put_global_server("hung", {"url": "https://one.test/mcp"})
    put_global_server("notes", {"url": "https://two.test/mcp"})
    cancelled = asyncio.Event()

    async def ensure(server, *, interactive=False):
        if server.name == "hung":
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        return SimpleNamespace(tools=[_tool("read_page")])

    monkeypatch.setattr(manager.mcp, "ensure", ensure)
    monkeypatch.setattr(manager_module, "_MCP_CONNECT_TIMEOUT", 0.01)
    await engine.prepare_turn()
    assert cancelled.is_set()
    assert engine.registry.get("mcp__notes__read_page") is not None
    assert '"hung": connection failed' in engine.mcp_context


async def test_client_loads_all_tool_pages_and_reconnects_when_transport_changes(monkeypatch):
    from coworker.mcp import client

    sessions = []

    @asynccontextmanager
    async def transport(*args, **kwargs):
        yield (None, None)

    class Session:
        def __init__(self, *args):
            self.closed = False
            sessions.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            self.closed = True

        async def initialize(self):
            return None

        async def list_tools(self, cursor=None):
            return SimpleNamespace(
                tools=[_tool("second" if cursor else "first")],
                nextCursor=None if cursor else "page-2",
            )

    monkeypatch.setattr(client, "streamablehttp_client", transport)
    monkeypatch.setattr(client, "ClientSession", Session)
    manager = MCPManager()
    server = MCPServerDef(name="notes", transport="http", url="https://one.test/mcp")
    first = await manager.ensure(server)
    assert [tool.name for tool in first.tools] == ["first", "second"]
    server.exclude_tools = ["first"]
    assert await manager.ensure(server) is first
    server.url = "https://two.test/mcp"
    second = await manager.ensure(server)
    assert second is not first
    assert sessions[0].closed
    await manager.close("notes")
    assert sessions[1].closed
    assert "notes" not in manager._conns
    third = await manager.ensure(server)
    assert third is not second
    await manager.aclose()
    assert sessions[-1].closed


async def test_an_interactive_connection_does_not_lock_other_servers(monkeypatch):
    from coworker.mcp.client import _Conn

    manager = MCPManager()
    started = asyncio.Event()

    async def serve(server, ready, *, interactive=False):
        conn = _Conn(None, [_tool("read_page")], server)
        try:
            if interactive:
                started.set()
                await asyncio.Event().wait()
            ready.set_result(conn)
            await conn.shutdown.wait()
        finally:
            if not ready.done():
                ready.cancel()
            manager._conns.pop(server.name, None)
            manager._tasks.pop(server.name, None)

    monkeypatch.setattr(manager, "_serve", serve)
    signing_in = asyncio.create_task(manager.ensure(
        MCPServerDef(name="signing-in", transport="http", url="https://one.test/mcp"),
        interactive=True,
    ))
    await started.wait()
    server = MCPServerDef(name="notes", transport="http", url="https://two.test/mcp")
    conn = await asyncio.wait_for(manager.ensure(server), 1)
    assert await asyncio.wait_for(manager.ensure(server), 1) is conn
    signing_in.cancel()
    await asyncio.gather(signing_in, return_exceptions=True)
    assert "signing-in" not in manager._tasks
    await manager.aclose()
