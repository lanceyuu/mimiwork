"""MCPManager — our own thin async MCP client over the official `mcp` SDK.

Async-native (no `nest_asyncio`, no second event loop): each server runs in a dedicated
asyncio task that opens the transport + `ClientSession`, keeps them alive until shutdown,
then closes them in the *same* task — required because the SDK's transports use anyio cancel
scopes that must be entered and exited on one task. Tool calls are awaited from any task on
the same loop, which is safe.

Tool execution from the (sync) ToolRegistry bridges back here via
`run_coroutine_threadsafe` — see `coworker/mcp/tools.py`.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from copy import deepcopy
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from .config import MCPServerDef


class _Conn:
    def __init__(self, session: ClientSession, tools: list[Any], server: MCPServerDef) -> None:
        self.session = session
        self.tools = tools  # list[mcp.types.Tool]
        self.server = deepcopy(server)
        self.shutdown = asyncio.Event()


class MCPManager:
    """Owns persistent MCP connections keyed by server name; lazy-connects on demand."""

    def __init__(self, secrets: Any = None) -> None:
        self._conns: dict[str, _Conn] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._oauth_lock = asyncio.Lock()
        # SecretStore for OAuth servers' token persistence (mcp/oauth.py); lazy default
        # so library/CLI construction without secrets keeps working.
        self._secrets = secrets

    async def ensure(self, server: MCPServerDef, *, interactive: bool = False) -> _Conn:
        """Return a live connection for `server`, connecting (once) if needed.

        `interactive=True` (explicit connect actions only) lets an OAuth server run
        the browser sign-in flow; the default refuses it — stored tokens and silent
        refresh still work, but a server that insists on re-authorization raises
        InteractiveAuthRequired instead of hijacking the user's browser.
        """
        async with AsyncExitStack() as stack:
            # OAuth callbacks share one pending slot; unrelated connections stay usable.
            if interactive:
                await stack.enter_async_context(self._oauth_lock)
            await stack.enter_async_context(self._locks.setdefault(server.name, asyncio.Lock()))
            existing = self._conns.get(server.name)
            if existing is not None:
                if not existing.shutdown.is_set() and all(
                    getattr(existing.server, key) == getattr(server, key)
                    for key in ("transport", "command", "args", "env", "cwd", "url", "headers", "auth")
                ):
                    return existing
                await self._close(server.name)
            ready: asyncio.Future = asyncio.get_running_loop().create_future()
            self._tasks[server.name] = asyncio.create_task(
                self._serve(server, ready, interactive=interactive)
            )
            try:
                conn = await ready  # propagates connection errors
            except asyncio.CancelledError:
                task = self._tasks.get(server.name)
                if task is not None:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                raise
            self._conns[server.name] = conn
            return conn

    async def tools(self, server: MCPServerDef) -> list[Any]:
        return (await self.ensure(server)).tools

    async def call(
        self, name: str, tool: str, arguments: Optional[dict[str, Any]]
    ) -> Any:
        conn = self._conns.get(name)
        if conn is None:
            raise RuntimeError(f"MCP server not connected: {name}")
        result = await conn.session.call_tool(tool, arguments or {})
        return _result_payload(result)

    async def close(self, name: str) -> None:
        async with self._locks.setdefault(name, asyncio.Lock()):
            await self._close(name)

    async def _close(self, name: str) -> None:
        conn = self._conns.get(name)
        if conn is not None:
            conn.shutdown.set()
        task = self._tasks.get(name)
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except (asyncio.TimeoutError, Exception):
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self._conns.pop(name, None)
        self._tasks.pop(name, None)

    async def aclose(self) -> None:
        for name in list(self._tasks):
            await self.close(name)

    # -- per-server lifecycle (one task owns enter+exit) ------------------------
    async def _serve(
        self, server: MCPServerDef, ready: asyncio.Future, *, interactive: bool = False
    ) -> None:
        try:
            async with AsyncExitStack() as stack:
                if server.transport == "http":
                    if not server.url:
                        raise ValueError(
                            f"MCP server '{server.name}' is http but has no url"
                        )
                    auth = None
                    if server.auth == "oauth":
                        from ..secrets import SecretStore
                        from .oauth import build_auth

                        if self._secrets is None:
                            self._secrets = SecretStore()
                        auth = build_auth(
                            server.name,
                            server.url,
                            self._secrets,
                            interactive=interactive,
                        )
                    read, write, *_ = await stack.enter_async_context(
                        streamablehttp_client(
                            server.url, headers=server.headers or None, auth=auth
                        )
                    )
                else:
                    if not server.command:
                        raise ValueError(
                            f"MCP server '{server.name}' is stdio but has no command"
                        )
                    params = StdioServerParameters(
                        command=server.command,
                        args=server.args,
                        env=server.env or None,
                        cwd=server.cwd,
                    )
                    read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                listed = await session.list_tools()
                tools = list(listed.tools)
                cursors: set[str] = set()
                while listed.nextCursor:
                    if listed.nextCursor in cursors:
                        raise RuntimeError("MCP server repeated its tool-list cursor")
                    cursors.add(listed.nextCursor)
                    listed = await session.list_tools(cursor=listed.nextCursor)
                    tools.extend(listed.tools)
                conn = _Conn(session, tools, server)
                if not ready.done():
                    ready.set_result(conn)
                await conn.shutdown.wait()
        except Exception as exc:  # connection / init failure
            if not ready.done():
                ready.set_exception(exc)
        finally:
            if not ready.done():
                ready.cancel()
            self._conns.pop(server.name, None)
            self._tasks.pop(server.name, None)


def _result_payload(result: Any) -> Any:
    """Flatten a CallToolResult into something the engine can serialize for the model."""
    texts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text is not None:
            texts.append(text)
        else:  # non-text content (image/resource) — describe it
            texts.append(f"[{getattr(block, 'type', 'content')}]")
    body = "\n".join(texts)
    if getattr(result, "isError", False):
        return {"error": body or "MCP tool error"}
    structured = getattr(result, "structuredContent", None)
    if structured is not None and not body:
        return structured
    return body
