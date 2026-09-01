"""Agents (Code/Chat) + SKILL.md loader (catalog + load_skill)."""

from __future__ import annotations

from coworker.agent import build_engine
from coworker.agents import AgentContext, chat_agent, code_agent, get_agent
from coworker.providers import ModelCapabilities
from coworker.skills import SkillLoader, skill_catalog_text, skill_tools
from coworker.tools import ToolRegistry
from coworker.tools.shell import LocalExecutor
from coworker.tools.todo import TodoList


class _Stub:
    def complete(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def capabilities(self, model):
        return ModelCapabilities()


# -- agents ---------------------------------------------------------------------


def test_code_agent_tools(tmp_path):
    ex = LocalExecutor(cwd=tmp_path, default_timeout=5)
    try:
        ctx = AgentContext(workspace=tmp_path, executor=ex, todo=TodoList())
        names = {getattr(t, "__name__", "?") for t in code_agent().build_tools(ctx)}
        assert {
            "read_file",
            "write_file",
            "git_status",
            "run_shell",
            "todo_write",
        } <= names
    finally:
        ex.close()


def test_chat_agent_has_no_workspace_tools():
    assert chat_agent().build_tools(AgentContext()) == []
    assert chat_agent().needs_workspace is False
    assert code_agent().needs_workspace is True


def test_get_agent_fallback():
    # Single-coworker app: legacy ids ("chat", "code") and unknown ids all
    # resolve to the one Cowork persona rather than erroring old sessions out.
    assert get_agent("chat").name == "cowork"
    assert get_agent("nope").name == "cowork"


# -- SKILL.md loader ------------------------------------------------------------


def _make_skill(skills_dir, name, desc, body):
    d = skills_dir / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n{body}", encoding="utf-8"
    )


def test_skill_loader_catalog_and_load(tmp_path):
    skills_dir = tmp_path / "skills"
    _make_skill(
        skills_dir, "pdf", "extract text from PDFs", "Use pdfplumber to extract text."
    )
    loader = SkillLoader([skills_dir])

    assert loader.catalog() == [
        {"name": "pdf", "description": "extract text from PDFs"}
    ]
    assert "pdf: extract text from PDFs" in skill_catalog_text(loader)

    reg = ToolRegistry()
    reg.register_all(skill_tools(loader))
    loaded = reg.execute("load_skill", {"name": "pdf"})
    assert "pdfplumber" in loaded["instructions"]
    assert reg.execute("load_skill", {"name": "missing"})["error"]


# -- engine assembly per agent --------------------------------------------------


def test_build_engine_chat(tmp_path):
    engine = build_engine(agent=chat_agent(), provider=_Stub())
    assert "load_skill" in engine.registry.names()
    assert "read_file" not in engine.registry.names()
    assert engine.executor is None
    assert engine.agent_name == "chat"


def test_build_engine_code_has_agents_md_and_skills(tmp_path):
    (tmp_path / "AGENTS.md").write_text("PROJECT RULE: prefer pathlib.")
    engine = build_engine(agent=code_agent(), workspace=tmp_path, provider=_Stub())
    try:
        assert "prefer pathlib" in engine.messages[0]["content"]
        assert "todo_write" in engine.registry.names()
        assert "load_skill" in engine.registry.names()
        assert engine.agent_name == "code"
    finally:
        engine.executor.close()


# ── asset bundles (v0.4.19) ───────────────────────────────────────────────────
# Asset-heavy skills ship their libraries as ONE archive. ppt-master alone carries
# ~3,200 icon SVGs, and shipping those loose pushed the app past 11,800 files —
# enough that the Windows MSI build died inside WiX's light.exe with no error.


def _bundle(tmp_path, entries: dict[str, str], name="libraries.bundle.zip"):
    import zipfile

    src = tmp_path / "builtin" / "asset-skill"
    (src / "templates").mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: asset-skill\ndescription: a skill with a packed library\n---\n\nBody.",
        encoding="utf-8",
    )
    with zipfile.ZipFile(src / "templates" / name, "w") as z:
        for path, body in entries.items():
            z.writestr(path, body)
    return src.parent


def _seeded(tmp_path, builtin_root):
    """Seed by copying the fixture: _seed_builtin reads the package's own builtin dir,
    so this exercises the copy-then-expand path with a skill we control."""
    import shutil

    from coworker.skills.store import SkillStore

    store = SkillStore(global_dir=tmp_path / "skills")
    target = store.global_dir / "asset-skill"
    shutil.copytree(builtin_root / "asset-skill", target)
    store._expand_bundles(target)
    return target


def test_a_packed_library_is_expanded_where_the_skill_expects_it(tmp_path):
    root = _bundle(tmp_path, {"icons/home.svg": "<svg/>", "icons/star.svg": "<svg/>"})
    target = _seeded(tmp_path, root)

    # Exactly the layout upstream's scripts reference — nothing in the skill is patched.
    assert (target / "templates" / "icons" / "home.svg").read_text() == "<svg/>"
    assert (target / "templates" / "icons" / "star.svg").exists()
    # And the archive is gone: it would otherwise ship twice on the user's disk.
    assert not (target / "templates" / "libraries.bundle.zip").exists()


def test_an_archive_cannot_write_outside_its_own_directory(tmp_path):
    """A zip is data. One naming its way up the tree must not land there."""
    root = _bundle(tmp_path, {"../../escaped.svg": "<svg/>", "icons/ok.svg": "<svg/>"})
    target = _seeded(tmp_path, root)

    assert not (target.parent / "escaped.svg").exists()
    assert not (target / "escaped.svg").exists()
    # Refused wholesale rather than half-extracted, and the archive stays for diagnosis.
    assert (target / "templates" / "libraries.bundle.zip").exists()


def test_a_corrupt_archive_leaves_the_rest_of_the_skill_usable(tmp_path):
    """The icons are one feature of a skill, not the whole thing."""
    from coworker.skills.store import SkillStore

    src = tmp_path / "builtin" / "asset-skill"
    (src / "templates").mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: asset-skill\ndescription: a skill with a broken library\n---\n\nBody.",
        encoding="utf-8",
    )
    (src / "templates" / "libraries.bundle.zip").write_bytes(b"not a zip at all")

    store = SkillStore(global_dir=tmp_path / "skills")
    import shutil

    target = store.global_dir / "asset-skill"
    shutil.copytree(src, target)
    store._expand_bundles(target)  # must not raise

    assert (target / "SKILL.md").is_file()
    rows = {r["name"]: r for r in store.rows()}
    assert "asset-skill" in rows
