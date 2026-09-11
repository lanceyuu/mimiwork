"""Per-turn facts a synchronous tool may need, carried into worker threads by contextvars."""

from contextvars import ContextVar
from typing import Optional

# The model answering the turn ("qualitati_cn:mimi-puppy"): the QualiTaTi data tools talk
# to that model's site, so a conversation on 质见中国 reads and writes 质见中国 projects.
tool_model: ContextVar[Optional[str]] = ContextVar("tool_model", default=None)
