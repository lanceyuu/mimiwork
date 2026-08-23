"""TRANSFER PACK — the surface that makes MimiWork's vocabulary the same as Claude Code's,
Cowork's and Codex's: saved `/commands`, global instructions, `@` file mentions and
importing skills that were written for those tools (owner ask 2026-08-23).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from coworker.project import load_agents_md
from coworker.providers import ModelCapabilities, ProviderClient
from coworker.server import SessionManager, create_app


class _StubProvider(ProviderClient):
    def complete(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def capabilities(self, model):
        return ModelCapabilities()


def _fixture(tmp_path, monkeypatch=None):
    manager = SessionManager(workspace=tmp_path, provider=_StubProvider())
    return TestClient(create_app(manager)), manager


def _open(client, path):
    assert client.post("/v1/workspaces/open", json={"path": str(path)}).json()["ok"]


def _command(folder: Path, name: str, body: str, description: str = "") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}\n", encoding="utf-8"
    )


# -- instruction files ---------------------------------------------------------------


def test_claude_md_is_read_alongside_agents_md(tmp_path):
    """A folder set up for Claude Code works here untouched, and vice-versa."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "AGENTS.md").write_text("Cite in APA 7.\n", encoding="utf-8")
    (ws / "CLAUDE.md").write_text("Never touch data/raw.\n", encoding="utf-8")
    home = tmp_path / "state"
    home.mkdir()
    (home / "CLAUDE.md").write_text("Answer in British English.\n", encoding="utf-8")

    block = load_agents_md(ws, global_path=home / "AGENTS.md")
    assert "Cite in APA 7." in block
    assert "Never touch data/raw." in block
    assert "Answer in British English." in block  # global CLAUDE.md counts too
    # AGENTS.md is injected before CLAUDE.md at project scope.
    assert block.index("Cite in APA 7.") < block.index("Never touch data/raw.")


def test_empty_instruction_files_add_nothing(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "CLAUDE.md").write_text("   \n", encoding="utf-8")
    assert load_agents_md(ws, global_path=tmp_path / "none" / "AGENTS.md") == ""


def test_global_instructions_round_trip(tmp_path):
    client, manager = _fixture(tmp_path)
    assert client.get("/v1/instructions").json()["instructions"] == ""
    saved = client.put("/v1/instructions", json={"instructions": "Always use metric.\n"})
    assert saved.json()["ok"]
    assert client.get("/v1/instructions").json()["instructions"].strip() == "Always use metric."
    # Emptying the editor removes the file rather than leaving a blank block behind.
    assert client.put("/v1/instructions", json={"instructions": "  "}).json()["ok"]
    assert client.get("/v1/instructions").json()["instructions"] == ""
    assert not Path(manager.global_instructions()["path"]).exists()


# -- saved commands ------------------------------------------------------------------


def test_commands_list_and_expand_arguments(tmp_path):
    client, manager = _fixture(tmp_path)
    proj = tmp_path / "thesis"
    proj.mkdir()
    _open(client, proj)
    _command(
        proj / ".coworker" / "commands",
        "weekly",
        "Write the weekly report for $ARGUMENTS.",
        description="Weekly report",
    )
    from coworker.secrets import state_dir

    _command(state_dir() / "commands", "tidy", "Tidy up $ARGUMENTS.", description="Tidy")

    rows = client.get("/v1/commands", params={"workspace": str(proj)}).json()["commands"]
    by_name = {r["name"]: r for r in rows}
    assert by_name["weekly"]["scope"] == "project"
    assert by_name["weekly"]["description"] == "Weekly report"
    assert by_name["tidy"]["scope"] == "global"
    assert rows[0]["name"] == "weekly"  # project commands first

    out = client.post(
        "/v1/commands/expand",
        json={"name": "weekly", "arguments": "Q3", "workspace": str(proj)},
    ).json()
    assert out["ok"] and out["text"] == "Write the weekly report for Q3."


def test_expanding_an_unknown_command_is_an_error_not_a_crash(tmp_path):
    client, _ = _fixture(tmp_path)
    out = client.post("/v1/commands/expand", json={"name": "nope"}).json()
    assert not out["ok"] and "nope" in out["error"]


# -- @ file mentions -----------------------------------------------------------------


def test_file_search_is_scoped_to_the_granted_folder(tmp_path):
    client, _ = _fixture(tmp_path)
    proj = tmp_path / "thesis"
    (proj / "chapters").mkdir(parents=True)
    (proj / "chapters" / "intro.docx").write_bytes(b"x")
    (proj / "notes.md").write_text("hi", encoding="utf-8")
    (proj / "node_modules").mkdir()
    (proj / "node_modules" / "intro.js").write_text("x", encoding="utf-8")
    outside = tmp_path / "private"
    outside.mkdir()
    (outside / "intro-secret.txt").write_text("no", encoding="utf-8")
    _open(client, proj)

    hits = client.get(
        "/v1/files/search", params={"q": "intro", "workspace": str(proj)}
    ).json()["files"]
    paths = [h["path"] for h in hits]
    assert "chapters/intro.docx" in paths
    assert not any("secret" in p for p in paths)  # never leaves the granted root
    assert not any("node_modules" in p for p in paths)  # build noise is pruned

    everything = client.get(
        "/v1/files/search", params={"q": "", "workspace": str(proj)}
    ).json()["files"]
    assert {"notes.md", "chapters/intro.docx"} <= {h["path"] for h in everything}


def test_file_search_without_a_folder_returns_nothing(tmp_path):
    client, _ = _fixture(tmp_path)
    assert client.get("/v1/files/search", params={"q": "x"}).json()["files"] == []


# -- importing Claude Code / Cowork skills -------------------------------------------


def _claude_skill(home: Path, name: str, description: str) -> Path:
    folder = home / ".claude" / "skills" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nDo the thing.\n",
        encoding="utf-8",
    )
    (folder / "reference.md").write_text("extra resource", encoding="utf-8")
    return folder


def test_importable_skills_are_found_and_copied_with_their_resources(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    source = _claude_skill(home, "brand-voice", "Write in the house voice")
    client, manager = _fixture(tmp_path)

    found = client.get("/v1/skills/importable").json()["skills"]
    row = next(r for r in found if r["name"] == "brand-voice")
    assert row["source"] == "Claude Code" and not row["installed"]

    done = client.post("/v1/skills/import", json={"path": str(source)}).json()
    assert done["ok"], done
    installed = Path(done["path"])
    assert (installed / "SKILL.md").is_file()
    assert (installed / "reference.md").is_file()  # resources travel with the skill
    assert any(s["name"] == "brand-voice" for s in manager.list_skills())
    # Now it shows as installed, and a second import is refused rather than clobbering.
    assert next(
        r for r in client.get("/v1/skills/importable").json()["skills"]
        if r["name"] == "brand-voice"
    )["installed"]
    again = client.post("/v1/skills/import", json={"path": str(source)}).json()
    assert not again["ok"] and "already exists" in again["error"]


def test_plugin_skills_are_importable_and_named_by_their_plugin(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    folder = home / ".claude" / "plugins" / "marketing" / "skills" / "ad-copy"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: ad-copy\ndescription: Write ads\n---\nBody.\n", encoding="utf-8"
    )
    client, _ = _fixture(tmp_path)
    row = next(
        r for r in client.get("/v1/skills/importable").json()["skills"] if r["name"] == "ad-copy"
    )
    assert row["source"] == "plugin: marketing"


def test_discovery_finds_the_layouts_that_actually_exist_on_disk(tmp_path, monkeypatch):
    """Regression (owner report 2026-08-23: "it does not find my claude skills"). Real
    machines carry at least three shapes — a marketplace whose skills sit DIRECTLY under
    it (no `skills/` segment), a plugin with one, and Codex's own folder. Assuming a shape
    found a fraction of what was there; discovery walks instead."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    def _skill(folder: Path, name: str) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: d\n---\nBody.\n", encoding="utf-8"
        )

    _skill(home / ".claude" / "plugins" / "marketplaces" / "daymade-skills" / "transcript-fixer",
           "transcript-fixer")
    _skill(home / ".claude" / "plugins" / "repos" / "acme" / "skills" / "deck-review", "deck-review")
    _skill(home / ".codex" / "skills" / "migrate-to-codex", "migrate-to-codex")
    # Resources inside a skill are not skills of their own.
    _skill(home / ".claude" / "skills" / "brand", "brand")
    (home / ".claude" / "skills" / "brand" / "examples").mkdir()
    (home / ".claude" / "skills" / "brand" / "examples" / "SKILL.md").write_text(
        "---\nname: nested\n---\nx\n", encoding="utf-8"
    )

    client, _ = _fixture(tmp_path)
    rows = {r["name"]: r for r in client.get("/v1/skills/importable").json()["skills"]}
    assert rows["transcript-fixer"]["source"] == "plugin: daymade-skills"
    assert rows["deck-review"]["source"] == "plugin: acme"
    assert rows["migrate-to-codex"]["source"] == "Codex"
    assert rows["brand"]["source"] == "Claude Code"
    assert "nested" not in rows  # a skill folder's children are its resources

    # And a discovered skill in any of those layouts really imports.
    done = client.post(
        "/v1/skills/import", json={"path": rows["migrate-to-codex"]["path"]}
    ).json()
    assert done["ok"], done


def test_import_refuses_a_folder_outside_the_known_skill_locations(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    rogue = tmp_path / "elsewhere" / "evil"
    rogue.mkdir(parents=True)
    (rogue / "SKILL.md").write_text("---\nname: evil\n---\nx\n", encoding="utf-8")
    client, _ = _fixture(tmp_path)
    out = client.post("/v1/skills/import", json={"path": str(rogue)}).json()
    assert not out["ok"] and "importable skill location" in out["error"]
