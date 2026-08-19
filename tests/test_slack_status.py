"""Slack/GitHub status after the managed-relay removal: manual credentials only."""

from coworker.secrets import SecretStore
from coworker.server.manager import SessionManager


def _manager(tmp_path):
    m = SessionManager.__new__(SessionManager)
    m.secrets = SecretStore(tmp_path / "secrets.json")
    return m


def test_slack_disconnected_by_default(tmp_path):
    status = _manager(tmp_path).slack_status()
    assert status == {"ok": True, "mode": "", "connected": False}


def test_slack_connected_with_manual_socket_mode_tokens(tmp_path):
    m = _manager(tmp_path)
    m.secrets.put("slack:default", {"bot_token": "xoxb-1", "app_token": "xapp-1"})
    assert m.slack_status()["connected"] is True


def test_leftover_relay_profile_is_not_connected(tmp_path):
    """A relay-mode profile predating the cloud removal must read as dead, not live."""
    m = _manager(tmp_path)
    m.secrets.put("slack:default", {"mode": "relay"})
    status = m.slack_status()
    assert status["connected"] is False
    assert status["mode"] == "relay"


def test_github_connected_only_with_a_manual_pat(tmp_path):
    m = _manager(tmp_path)
    assert m.github_status()["connected"] is False
    m.secrets.put("github:default", {"token": "ghp_x"})
    assert m.github_status()["connected"] is True
    m.secrets.put("github:default", {"mode": "relay"})
    assert m.github_status()["connected"] is False
