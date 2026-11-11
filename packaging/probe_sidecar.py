"""Prove a frozen sidecar can run the analysis kernel and take its launch token before it ships.

    python packaging/probe_sidecar.py dist/openworker-server/openworker-server

Tests run from source, where `python -m` always works; only the frozen binary can show that
the kernel launches and that the analysis stack really made it into the bundle. The same
goes for the launch token: the desktop app sends it on the sidecar's standard input, and a
frozen binary that cannot read it there leaves every user with a window that never loads.
Run by both build scripts right after PyInstaller. Exits non-zero, saying what failed,
otherwise.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

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


def _status(url: str, token: str | None = None) -> int | None:
    """The HTTP status the sidecar answers with, or None while nothing is listening."""
    request = urllib.request.Request(url, headers={"X-OpenWorker-Token": token} if token else {})
    # No proxy: a build machine's proxy settings must not stand between us and loopback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=10) as reply:
            return reply.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except OSError:
        return None


def launch_token_probe(binary: str) -> int:
    """Start the server the way the desktop app does and check the token it was sent on
    standard input is the one that opens it."""
    token = secrets.token_hex(32)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/v1/sessions"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        env = {
            **os.environ,
            "COWORKER_TOKEN_ON_STDIN": "1",
            "COWORKER_STATE_DIR": os.path.join(work, "state"),
            "COWORKER_SEED_BUILTIN_SKILLS": "0",
            "COWORKER_SEED_BUILTIN_APPS": "0",
        }
        env.pop("COWORKER_API_TOKEN", None)
        log_path = os.path.join(work, "server.log")
        without = with_token = None
        with open(log_path, "wb") as log:
            server = subprocess.Popen(
                [binary, "--host", "127.0.0.1", "--port", str(port), "--cwd", work],
                stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, env=env,
                # The desktop app starts it without a console window on Windows.
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                server.stdin.write((token + "\n").encode())
                server.stdin.close()
                deadline = time.monotonic() + 180
                while server.poll() is None and time.monotonic() < deadline:
                    without = _status(url)
                    if without is not None:
                        break
                    time.sleep(0.5)
                if without is not None:
                    with_token = _status(url, token)
            finally:
                server.kill()
                server.wait()
        with open(log_path, errors="replace") as log:
            output = log.read()
    if (without, with_token) != (401, 200):
        print(
            "launch token on standard input did not work: "
            f"without it the server answered {without}, with it {with_token}\n{output}",
            file=sys.stderr,
        )
        return 1
    print("launch token on standard input OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) or launch_token_probe(sys.argv[1]))
