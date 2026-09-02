"""Apps — small HTML tools Mimi writes and the user runs inside MimiWork.

One HTML file per app, a manifest beside it, and a bridge (``window.Mimi``) the GUI
injects so the page can ask the model and remember state. Design:
docs/superpowers/specs/2026-09-03-apps-section-design.md.
"""

from .store import App, AppStore, validate_html
from .tools import app_tools

__all__ = ["App", "AppStore", "app_tools", "validate_html"]
