"""Per-turn facts a synchronous tool may need, carried into worker threads by contextvars."""

from contextvars import ContextVar
from typing import Callable, Optional

# The model answering the turn ("qualitati_cn:mimi-puppy"): the QualiTaTi data tools talk
# to that model's site, so a conversation on 质见中国 reads and writes 质见中国 projects.
tool_model: ContextVar[Optional[str]] = ContextVar("tool_model", default=None)

# Where a long-running tool reports a progress line ("Running: pytest"). The engine sets it
# around a call and turns each line into a display-only TOOL_PROGRESS event; outside a turn
# it is None and the tool stays quiet.
tool_progress: ContextVar[Optional[Callable[[str], None]]] = ContextVar("tool_progress", default=None)
