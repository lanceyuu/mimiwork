"""Per-call cancellation, propagated into synchronous tool workers by contextvars."""

from contextvars import ContextVar
from threading import Event

# A fresh event belongs to each turn. An old worker must never see a later turn's
# cleared stop flag and resume work that the user already stopped.
tool_stop: ContextVar[Event | None] = ContextVar("tool_stop", default=None)
