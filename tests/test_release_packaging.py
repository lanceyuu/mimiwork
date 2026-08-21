"""Release-workflow invariants for features promised by the desktop installers."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".github" / "workflows" / "release.yml"


def test_release_bundle_installs_and_probes_messaging_dependencies():
    workflow = RELEASE.read_text(encoding="utf-8")

    assert '".[bedrock,knowledge,messaging]"' in workflow
    assert "import aiohttp, aisuite, coworker, slack_bolt, telegram" in workflow


def test_release_build_waits_for_verification_job():
    workflow = RELEASE.read_text(encoding="utf-8")

    assert "  verify:\n" in workflow
    assert "  build:\n    needs: verify\n" in workflow
    assert "npm run e2e" in workflow
