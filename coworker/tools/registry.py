"""Tool registry — wraps callables (incl. aisuite toolkit tools) into a registry the
runtime owns: JSON schemas for the model, plus execution. Permission checks live in the
PermissionEngine and are applied by the turn engine, not here.

Schema generation is reused from aisuite (`Tools`) so we don't reimplement
docstring/type-hint → JSON-schema extraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from aisuite.utils.tools import Tools


class RecoveryPolicy(str, Enum):
    """What the engine may do when a process dies while a tool is running.

    Exactly-once execution is impossible for arbitrary external side effects.  The
    safe default is therefore to stop on an ambiguous outcome.  Only tools whose
    contract is read-only may be replayed automatically.
    """

    REPLAY_SAFE = "replay_safe"
    NON_REPLAYABLE = "non_replayable"


@dataclass
class ToolSpec:
    name: str
    schema: dict[str, Any]  # OpenAI-format function tool schema
    func: Callable[..., Any]
    metadata: Any = None  # aisuite ToolMetadata or None
    recovery_policy: RecoveryPolicy = RecoveryPolicy.NON_REPLAYABLE


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        func: Callable[..., Any],
        *,
        metadata: Any = None,
        schema: Optional[dict[str, Any]] = None,
        recovery_policy: Optional[RecoveryPolicy | str] = None,
    ) -> ToolSpec:
        name = getattr(func, "__name__", None)
        if not name:
            raise ValueError("Tool function must have a __name__.")
        meta = metadata or getattr(func, "__aisuite_tool_metadata__", None)
        # Allow an explicit schema override (param or a `__coworker_schema__` attribute)
        # for tools whose signature can't be auto-converted to a valid JSON schema.
        resolved_schema = (
            schema or getattr(func, "__coworker_schema__", None) or _schema_for(func)
        )
        policy = _recovery_policy_for(func, meta, recovery_policy)
        spec = ToolSpec(
            name=name,
            schema=resolved_schema,
            func=func,
            metadata=meta,
            recovery_policy=policy,
        )
        self._tools[name] = spec
        return spec

    def register_all(self, funcs: list[Callable[..., Any]]) -> None:
        for func in funcs:
            self.register(func)

    def names(self) -> list[str]:
        return list(self._tools)

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [spec.schema for spec in self._tools.values()]

    def execute(self, name: str, arguments: Optional[dict[str, Any]] = None) -> Any:
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"Tool not registered: {name}")
        try:
            return spec.func(**(arguments or {}))
        except TypeError as exc:
            # A call that does not fit the signature ("unexpected keyword argument
            # 'timeout'") gets the parameter list back, so the model corrects the call
            # instead of guessing again. A TypeError from inside the tool is left alone.
            text = str(exc)
            if "argument" in text and ("unexpected" in text or "required" in text):
                import inspect

                params = ", ".join(inspect.signature(spec.func).parameters)
                raise TypeError(
                    f"{name} was called with the wrong arguments ({text}). "
                    f"Its parameters are: {params}"
                ) from exc
            raise


def _schema_for(func: Callable[..., Any]) -> dict[str, Any]:
    """Generate one OpenAI-format tool schema via aisuite's schema generator."""
    return Tools([func]).tools(format="openai")[0]


def _recovery_policy_for(
    func: Callable[..., Any], metadata: Any, explicit: Optional[RecoveryPolicy | str]
) -> RecoveryPolicy:
    configured = explicit or getattr(func, "__coworker_recovery_policy__", None)
    if configured is not None:
        return RecoveryPolicy(configured)

    # Infer only the narrow, auditable read-only families already described by
    # tool metadata.  "low risk" alone is insufficient: todo updates and process
    # controls are low-risk but still mutate state.
    capabilities = set(getattr(metadata, "capabilities", None) or [])
    if (
        capabilities
        and capabilities <= {"read", "search", "git"}
        and not getattr(metadata, "requires_approval", False)
    ):
        return RecoveryPolicy.REPLAY_SAFE
    return RecoveryPolicy.NON_REPLAYABLE
