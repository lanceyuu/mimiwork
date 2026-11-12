"""Keys a person saves for their own scripts.

A script the person asks Mimi to run often needs a key of theirs (an API key for a service
they pay for). MimiWork is started from the Dock, so nothing set in their Terminal reaches
it, and a key typed into the chat is sent to the model and kept in the conversation. These
are saved in Settings instead and handed to the shell and the Python kernel as environment
variables. The model is told the names, never the values, and a value that a script prints
is hidden before the model or the conversation file sees it.

This is separate from the provider keys MimiWork chats with: those are never given to
scripts.
"""

from __future__ import annotations

import re
from typing import Any, Optional

PROFILE = "script-keys"
MAX_VALUE = 4096
_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
# A name here does not hand a program a secret, it changes which program runs or what it
# loads. Saving one would let a pasted "key" take over every command Mimi runs.
_RESERVED = {
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "PWD", "OLDPWD", "IFS", "ENV", "TERM",
    "TMPDIR", "TEMP", "TMP", "LANG", "EDITOR", "VISUAL", "PAGER", "PROMPT_COMMAND",
    "APPDATA", "LOCALAPPDATA", "USERPROFILE", "SYSTEMROOT", "COMSPEC", "PATHEXT",
    "MPLBACKEND", "PS1", "PS2", "PS4",
}
_RESERVED_STARTS = (
    "LD_", "DYLD_", "PYTHON", "NODE_", "NPM_", "GIT_", "BASH_", "LC_", "R_",
    "COWORKER_", "OPENWORKER_", "MIMIWORK_",
)
# Shorter than this and hiding the value would blank out ordinary words in a result.
_MIN_HIDDEN = 8


def name_problem(name: str) -> Optional[str]:
    """Why this name cannot be used, in words for the person, or None when it can."""
    if not _NAME.match(name or ""):
        return "Use capital letters, digits and underscores, starting with a letter, such as OPENROUTER_API_KEY."
    if name in _RESERVED or name.startswith(_RESERVED_STARTS):
        return "That name is used by the computer itself. Choose the name your script expects for its key."
    return None


def load(store: Any = None) -> dict[str, str]:
    from .secrets import SecretStore

    try:
        data = (store or SecretStore()).get(PROFILE) or {}
    except Exception:
        return {}  # an unreadable store must not stop a command from running
    return {k: v for k, v in data.items() if isinstance(v, str) and v and not name_problem(k)}


def save(store: Any, name: str, value: str) -> Optional[str]:
    """Save one key. Returns the problem in words, or None when it was saved."""
    name, value = (name or "").strip(), (value or "").strip()
    problem = name_problem(name)
    if problem:
        return problem
    if not value or len(value) > MAX_VALUE or any(c in value for c in "\r\n\0"):
        return "The key must be one line of text."
    store.put(PROFILE, {**load(store), name: value})
    return None


def remove(store: Any, name: str) -> None:
    keys = load(store)
    if keys.pop(name, None) is None:
        return
    if keys:
        store.put(PROFILE, keys)
    else:
        store.delete(PROFILE)


def hide(text: str, keys: Optional[dict[str, str]] = None) -> str:
    """The text with every saved value replaced by its name."""
    for name, value in (load() if keys is None else keys).items():
        if len(value) >= _MIN_HIDDEN and value in text:
            text = text.replace(value, f"[{name} hidden]")
    return text
