"""Prove a frozen sidecar can run the analysis kernel before it ships.

    python packaging/probe_sidecar.py dist/openworker-server/openworker-server

Tests run from source, where `python -m` always works; only the frozen binary can show that
the kernel launches and that the analysis stack really made it into the bundle. Run by both
build scripts right after PyInstaller. Exits non-zero, saying what failed, otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile

# The imports a user's analysis depends on; collect_all fails silently, so absence only
# shows up here or in a user's session.
PROBE = (
    "import pandas, numpy, scipy.stats, statsmodels.formula.api, matplotlib.pyplot, pyreadstat\n"
    "statsmodels.__version__"
)


def main(binary: str) -> int:
    with tempfile.TemporaryDirectory() as work:
        requests = json.dumps({"code": PROBE}) + "\n" + json.dumps({"shutdown": True}) + "\n"
        try:
            done = subprocess.run(
                [binary, "--analysis-kernel", work, work],
                input=requests, capture_output=True, text=True, timeout=180,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"analysis kernel probe could not run the sidecar: {exc}", file=sys.stderr)
            return 1
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    replies = []
    for line in lines:
        try:
            replies.append(json.loads(line))
        except ValueError:
            pass
    if len(replies) < 2 or not replies[0].get("ready"):
        print(f"analysis kernel did not start:\n{done.stdout}\n{done.stderr}", file=sys.stderr)
        return 1
    if not replies[1].get("ok"):
        print(f"analysis stack is incomplete: {replies[1].get('error')}", file=sys.stderr)
        return 1
    print(f"analysis kernel OK (statsmodels {replies[1].get('value')})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
