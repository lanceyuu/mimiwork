"""Apps on disk: ``apps/<id>/app.json`` + ``index.html`` (+ ``state.json``).

Folder-is-truth, no database — a dozen apps do not need one, and a folder the user
can open in Finder is the whole export story when everything else fails.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# An app may not fetch anything: the GUI's sandbox blocks it anyway, but refusing at the
# door tells the model (and an importer) WHY the page came up blank.
_EXTERNAL = re.compile(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", re.I)
MAX_HTML = 512 * 1024
MAX_STATE = 256 * 1024
MAX_PROMPT = 32 * 1024


def validate_html(html: str) -> Optional[str]:
    """Why this HTML cannot be an app, or None when it can."""
    if not isinstance(html, str) or not html.strip():
        return "the app is empty"
    if len(html.encode("utf-8")) > MAX_HTML:
        return "the app is larger than 512 KB — keep it to one small file"
    if _EXTERNAL.search(html):
        return (
            "the app loads something from the web (a script, stylesheet, font or image "
            "with an http(s) URL). Apps run without network — inline everything."
        )
    return None


@dataclass
class App:
    id: str
    title: str
    icon: str = "✨"
    description: str = ""
    model: Optional[str] = None
    builder_session: str = ""
    asks: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        return asdict(self)


class AppStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- paths ------------------------------------------------------------------
    def _dir(self, app_id: str) -> Path:
        # Ids are ours (app-<hex>); anything else is not a path we will build.
        if not re.fullmatch(r"app-[0-9a-f]{8}", app_id or ""):
            raise KeyError(app_id)
        return self.root / app_id

    # -- read -------------------------------------------------------------------
    def list(self) -> list[App]:
        out: list[App] = []
        for d in sorted(self.root.iterdir()) if self.root.is_dir() else []:
            app = self._load(d)
            if app is not None:
                out.append(app)
        return sorted(out, key=lambda a: -a.updated_at)

    def get(self, app_id: str) -> Optional[App]:
        try:
            return self._load(self._dir(app_id))
        except KeyError:
            return None

    def _load(self, d: Path) -> Optional[App]:
        try:
            data = json.loads((d / "app.json").read_text(encoding="utf-8"))
            return App(**{k: v for k, v in data.items() if k in App.__dataclass_fields__})
        except (OSError, ValueError, TypeError):
            return None

    def html(self, app_id: str) -> str:
        try:
            return (self._dir(app_id) / "index.html").read_text(encoding="utf-8")
        except (OSError, KeyError):
            return ""

    def state(self, app_id: str) -> dict[str, Any]:
        try:
            data = json.loads((self._dir(app_id) / "state.json").read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, KeyError):
            return {}

    # -- write ------------------------------------------------------------------
    def create(
        self,
        *,
        title: str,
        html: str,
        icon: str = "✨",
        description: str = "",
        builder_session: str = "",
        model: Optional[str] = None,
    ) -> App:
        problem = validate_html(html)
        if problem:
            raise ValueError(problem)
        app = App(
            id=f"app-{secrets.token_hex(4)}",
            title=(title or "Untitled app").strip()[:80],
            icon=(icon or "✨").strip()[:4] or "✨",
            description=(description or "").strip()[:300],
            model=(model or "").strip() or None,
            builder_session=builder_session or "",
        )
        d = self._dir(app.id)
        d.mkdir(parents=True, exist_ok=False)
        (d / "index.html").write_text(html, encoding="utf-8")
        self._save(app)
        return app

    def set_html(self, app_id: str, html: str) -> App:
        app = self.get(app_id)
        if app is None:
            raise KeyError(app_id)
        problem = validate_html(html)
        if problem:
            raise ValueError(problem)
        (self._dir(app_id) / "index.html").write_text(html, encoding="utf-8")
        app.updated_at = time.time()
        self._save(app)
        return app

    def update(self, app_id: str, **changes: Any) -> App:
        app = self.get(app_id)
        if app is None:
            raise KeyError(app_id)
        if changes.get("title") is not None:
            app.title = str(changes["title"]).strip()[:80] or app.title
        if changes.get("icon") is not None:
            app.icon = str(changes["icon"]).strip()[:4] or app.icon
        if changes.get("description") is not None:
            app.description = str(changes["description"]).strip()[:300]
        if "model" in changes:
            # "" clears the pin, like an automation's.
            app.model = (str(changes["model"] or "")).strip() or None
        if changes.get("builder_session") is not None:
            app.builder_session = str(changes["builder_session"])
        app.updated_at = time.time()
        self._save(app)
        return app

    def note_ask(self, app_id: str) -> None:
        app = self.get(app_id)
        if app is not None:
            app.asks += 1
            self._save(app)

    def set_state(self, app_id: str, value: dict[str, Any]) -> None:
        if not isinstance(value, dict):
            raise ValueError("state must be an object")
        raw = json.dumps(value)
        if len(raw.encode("utf-8")) > MAX_STATE:
            raise ValueError("state is larger than 256 KB")
        (self._dir(app_id) / "state.json").write_text(raw, encoding="utf-8")

    def delete(self, app_id: str) -> bool:
        try:
            d = self._dir(app_id)
        except KeyError:
            return False
        if not d.is_dir():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True

    def _save(self, app: App) -> None:
        (self._dir(app.id) / "app.json").write_text(
            json.dumps(app.public(), indent=2), encoding="utf-8"
        )


# -- export / import: one .mimiapp.html file ------------------------------------
_MANIFEST_RE = re.compile(
    r'<script type="application/json" id="mimi-app">(.*?)</script>\s*', re.S
)


def pack(app: App, html: str) -> str:
    """The share file: the manifest as a JSON block on top, the app below."""
    manifest = {
        "mimiwork_app": 1,
        "title": app.title,
        "icon": app.icon,
        "description": app.description,
    }
    return (
        f'<script type="application/json" id="mimi-app">{json.dumps(manifest)}</script>\n'
        + html
    )


def unpack(text: str) -> tuple[dict[str, Any], str]:
    """(manifest, html) from a share file; a bare HTML file gets an empty manifest."""
    m = _MANIFEST_RE.search(text or "")
    if not m:
        return {}, text or ""
    try:
        manifest = json.loads(m.group(1))
    except ValueError:
        manifest = {}
    return (manifest if isinstance(manifest, dict) else {}), text[: m.start()] + text[m.end() :]


def builtin_starters() -> list[dict[str, Any]]:
    """Bundled starter apps, as {name, title, icon, description, html}."""
    out: list[dict[str, Any]] = []
    for path in sorted((Path(__file__).parent / "starters").glob("*.mimiapp.html")):
        try:
            manifest, html = unpack(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if manifest.get("mimiwork_app") != 1 or not manifest.get("title"):
            continue
        out.append(
            {
                "name": path.name.removesuffix(".mimiapp.html"),
                "title": manifest["title"],
                "icon": manifest.get("icon") or "✨",
                "description": manifest.get("description") or "",
                "html": html,
            }
        )
    return out
