"""state_dir() survives a root-owned ~/.config (field report 2026-10-21: the sidecar died before
writing a log, so the app showed "Server unreachable" with an empty diagnostic log)."""

import os
import sys

import pytest

from coworker.secrets import state_dir

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="POSIX permissions; root ignores them"
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.delenv("COWORKER_STATE_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _fallback(home):
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "coworker"
    return home / ".local" / "state" / "coworker"


def test_writable_home_keeps_dot_config(home):
    assert state_dir() == home / ".config" / "coworker"


def test_unwritable_dot_config_falls_back_and_sticks(home):
    (home / ".config").mkdir(mode=0o555)
    try:
        d = state_dir()
        assert d == _fallback(home)
        (d / "logs").mkdir()  # actually writable
        # Fixing ~/.config later must not strand the data already in the fallback.
        (home / ".config").chmod(0o755)
        assert state_dir() == _fallback(home)
    finally:
        (home / ".config").chmod(0o755)


def test_existing_dot_config_data_wins(home):
    (home / ".config" / "coworker").mkdir(parents=True)
    _fallback(home).mkdir(parents=True)
    assert state_dir() == home / ".config" / "coworker"


def test_nothing_writable_names_the_fix(home):
    (home / ".config").mkdir(mode=0o555)
    (home / "Library").mkdir(mode=0o555)
    (home / ".local").mkdir(mode=0o555)
    try:
        with pytest.raises(PermissionError, match="sudo chown -R"):
            state_dir()
    finally:
        for p in (".config", "Library", ".local"):
            (home / p).chmod(0o755)
