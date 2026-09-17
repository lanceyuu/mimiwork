"""The frozen sidecar only ships the data files the PyInstaller spec names. Every folder
the server reads at runtime must be listed, or the feature silently vanishes from the
desktop app while working from source (the Apps gallery and the Radio app, 2026-09-17)."""

from pathlib import Path

SPEC = Path(__file__).resolve().parents[1] / "packaging" / "openworker-server.spec"
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

RUNTIME_DATA = [
    "**/*.md",  # personas/builtin
    "**/*.jsonl",  # kb
    "skills/builtin/**/*",
    "skills/*.json.gz",
    "skills/*.json",
    "blueprints/*.json",
    "apps/starters/*.mimiapp.html",
]


def test_every_runtime_data_folder_is_bundled():
    spec = SPEC.read_text(encoding="utf-8")
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    for pattern in RUNTIME_DATA:
        assert pattern in spec, f"{pattern} missing from the PyInstaller spec"
    for pattern in ("skills/builtin/**/*", "blueprints/*.json", "apps/starters/*.mimiapp.html"):
        assert pattern in pyproject, f"{pattern} missing from package-data"
