"""Agent-facing app tools: Mimi writes an app, or rewrites one after feedback.

Neither gates: they write only under the state dir's ``apps/`` folder, which is the
app's own bookkeeping, not the user's files. The origin session is recorded so
"Improve" on the app page can reopen the conversation that built it.
"""

from __future__ import annotations

from typing import Any, Callable

import aisuite as ai

from .store import AppStore

_CREATE = {
    "type": "function",
    "function": {
        "name": "create_app",
        "description": (
            "Save a new app: ONE self-contained HTML file the user runs inside MimiWork. "
            "No external scripts, styles, fonts or images — the app has no network. Use "
            "window.Mimi.ask(prompt) for anything that needs a model and "
            "Mimi.state.get()/set(obj) to remember things. Appears in the Apps section at once."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short name, e.g. 'Translator'."},
                "icon": {"type": "string", "description": "One emoji for the sidebar."},
                "description": {
                    "type": "string",
                    "description": "One sentence: what it does, for the overview card.",
                },
                "html": {"type": "string", "description": "The complete index.html."},
                "model": {
                    "type": "string",
                    "description": (
                        "Which model answers the app's Mimi.ask calls. Pass exactly what the "
                        "user's build request names; omit for the app default."
                    ),
                },
            },
            "required": ["title", "html"],
        },
    },
}

_UPDATE = {
    "type": "function",
    "function": {
        "name": "update_app",
        "description": (
            "Replace an existing app's HTML (the whole file, not a diff) after the user asked "
            "for a change. Title, icon and description are optional."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "The app id, e.g. 'app-1a2b3c4d'."},
                "html": {"type": "string", "description": "The complete new index.html."},
                "title": {"type": "string"},
                "icon": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["id", "html"],
        },
    },
}

_LIST = {
    "type": "function",
    "function": {
        "name": "list_apps",
        "description": "The user's apps (id, title, description).",
        "parameters": {"type": "object", "properties": {}},
    },
}


def _tool(func: Callable, schema: dict) -> Callable:
    func.__name__ = schema["function"]["name"]
    func.__doc__ = schema["function"]["description"]
    func.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name=schema["function"]["name"],
        category="apps",
        risk_level="low",
        capabilities=["apps"],
        requires_approval=False,
    )
    func.__coworker_schema__ = schema
    return func


def app_tools(store: AppStore, *, session_id: str = "") -> list[Callable[..., Any]]:
    def create_app(title, html, icon="✨", description="", model=None):
        try:
            app = store.create(
                title=title,
                html=html,
                icon=icon,
                description=description,
                builder_session=session_id,
                model=model,
            )
        except ValueError as e:
            return {"error": str(e)}
        return {"ok": True, "id": app.id, "title": app.title}

    def update_app(id, html, title=None, icon=None, description=None):
        try:
            store.set_html(id, html)
            app = store.update(id, title=title, icon=icon, description=description)
        except KeyError:
            return {"error": f"no app with id {id!r}"}
        except ValueError as e:
            return {"error": str(e)}
        return {"ok": True, "id": app.id, "title": app.title}

    def list_apps():
        return {
            "apps": [
                {"id": a.id, "title": a.title, "description": a.description}
                for a in store.list()
            ]
        }

    return [_tool(create_app, _CREATE), _tool(update_app, _UPDATE), _tool(list_apps, _LIST)]
