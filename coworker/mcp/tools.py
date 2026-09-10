"""Turn MCP tools into ToolRegistry-ready callables.

Each MCP tool becomes a sync callable (so it fits the registry's `execute` contract, which
the engine already runs via `asyncio.to_thread`). The callable bridges back to the live
async session on the server loop via `run_coroutine_threadsafe`. We attach `ToolMetadata`
(category="mcp", `requires_approval` per config) so the PermissionEngine gates it, and an
explicit OpenAI schema built straight from the MCP `inputSchema` for fidelity.
"""

from __future__ import annotations

import asyncio
import re
from concurrent.futures import TimeoutError as FutureTimeout
from time import monotonic
from typing import Any, Awaitable, Callable

import aisuite as ai

from ..tools.cancellation import tool_stop
from .config import MCPServerDef

CallAsync = Callable[[str, dict[str, Any]], Awaitable[Any]]

_NAME_OK = re.compile(r"[^a-zA-Z0-9_-]")
_MAX_NAME = 64  # OpenAI function-name limit


def tool_name(server: str, tool: str) -> str:
    """`mcp__<server>__<tool>`, sanitized to OpenAI's `[A-Za-z0-9_-]{1,64}` rule."""
    base = f"mcp__{_NAME_OK.sub('_', server)}__{_NAME_OK.sub('_', tool)}"
    if len(base) > _MAX_NAME:
        base = base[:_MAX_NAME]
    return base


def _openai_schema(name: str, mcp_tool: Any) -> dict[str, Any]:
    params = getattr(mcp_tool, "inputSchema", None) or {
        "type": "object",
        "properties": {},
    }
    description = (getattr(mcp_tool, "description", None) or "")[:1024]
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": params},
    }


def _filtered(mcp_tools: list[Any], server: MCPServerDef) -> list[Any]:
    out = mcp_tools
    if server.include_tools is not None:
        allow = set(server.include_tools)
        out = [t for t in out if t.name in allow]
    if server.exclude_tools:
        block = set(server.exclude_tools)
        out = [t for t in out if t.name not in block]
    return out


def build_callables(
    server: MCPServerDef,
    mcp_tools: list[Any],
    call_async: CallAsync,
    loop: asyncio.AbstractEventLoop,
    *,
    timeout: float = 120.0,
) -> list[Callable[..., Any]]:
    """Wrap a server's (filtered) MCP tools as registry-ready callables."""
    callables: list[Callable[..., Any]] = []
    for mcp_tool in _filtered(mcp_tools, server):
        name = tool_name(server.name, mcp_tool.name)
        remote = mcp_tool.name

        def _invoke(_remote: str = remote, **kwargs: Any) -> Any:
            stop = tool_stop.get()
            if stop is not None and stop.is_set():
                raise RuntimeError("interrupted by user")
            future = asyncio.run_coroutine_threadsafe(call_async(_remote, kwargs), loop)
            deadline = monotonic() + timeout
            try:
                while True:
                    if stop is not None and stop.is_set():
                        raise RuntimeError("interrupted by user")
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TimeoutError("The connected service did not respond in time")
                    try:
                        return future.result(min(0.1, remaining))
                    except FutureTimeout:
                        if future.done():
                            raise
            finally:
                # Cancel the actual MCP request too, not just its waiting worker.
                if not future.done():
                    future.cancel()

        # We attach the schema + metadata explicitly (rather than via `ai.tool`, which would
        # try to derive a schema from this `**kwargs` wrapper): the registry reads both attrs.
        _invoke.__name__ = name
        _invoke.__doc__ = (
            getattr(mcp_tool, "description", None)
            or f"MCP tool {remote} from {server.name}"
        )
        _invoke.__aisuite_tool_metadata__ = ai.ToolMetadata(
            name=name,
            category="mcp",
            risk_level="medium",
            capabilities=[server.name],
            requires_approval=server.requires_approval,
        )
        _invoke.__coworker_schema__ = _openai_schema(name, mcp_tool)
        callables.append(_invoke)
    return callables
