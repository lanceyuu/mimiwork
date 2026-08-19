"""Shared plumbing for the Office tools: tool decoration and optional-dependency probing."""

from __future__ import annotations

import importlib
from typing import Any, Callable, Optional

import aisuite as ai

# Model-visible caps. Office files routinely hold more text than a context window: a long
# report or a 200k-row sheet must be windowed rather than dumped, exactly as `read_file`
# windows a large text file.
MAX_CELL_CHARS = 400
MAX_TEXT_CHARS = 100_000


def decorate(
    func: Callable[..., Any],
    *,
    name: str,
    schema: dict[str, Any],
    risk: str = "low",
    approval: bool = False,
    capabilities: Optional[list[str]] = None,
) -> Callable[..., Any]:
    """Attach the metadata the registry and permission engine read off a tool callable.

    Mirrors ``tools/files.py``: an explicit ``__coworker_schema__`` wins over aisuite's
    docstring/type-hint inference, which cannot express the nested block shapes these tools take.
    """
    func.__name__ = name
    func.__doc__ = schema["function"]["description"]
    func.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name=name,
        category="office",
        risk_level=risk,
        capabilities=capabilities or ["read"],
        requires_approval=approval,
    )
    func.__coworker_schema__ = schema
    return func


def require(module: str, package: str, extra: str = "office") -> Any:
    """Import an optional dependency, or raise ``MissingDependency`` naming the install command."""
    try:
        return importlib.import_module(module)
    except ImportError as exc:  # pragma: no cover - exercised via guard()
        raise MissingDependency(
            f"{package} is not installed. Install it with: pip install 'coworker[{extra}]'"
        ) from exc


class MissingDependency(RuntimeError):
    """An optional Office/analysis library is absent. Carries the exact install command."""


def guard(func: Callable[..., Any]) -> Callable[..., Any]:
    """Turn the exceptions a tool body can raise into the ``{"error": ...}`` dicts the engine
    expects. Tools return errors as data — a raised exception becomes an opaque tool failure,
    while a returned error tells the model what to do next."""
    from .paths import PathError

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except MissingDependency as exc:
            return {"error": str(exc)}
        except PathError as exc:
            return {"error": str(exc)}
        except FileNotFoundError as exc:
            return {"error": f"file not found: {exc}"}
        except OSError as exc:
            return {"error": f"file error: {exc}"}
        except (ValueError, KeyError, TypeError) as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    wrapper.__wrapped__ = func
    return wrapper


def clip(text: Any, limit: int = MAX_CELL_CHARS) -> Any:
    """Bound one model-visible string; non-strings pass through untouched."""
    if not isinstance(text, str) or len(text) <= limit:
        return text
    return text[:limit] + "… (truncated)"
