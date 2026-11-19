"""Ask the real app for a slide deck and keep what came back: the file, a picture of every
slide, how long it took and which tools ran.

Manual, before a release. Needs the network and a QualiTaTi sign-in on this computer:
    .venv/bin/python scripts/live_deck.py [case ...] [--model qualitati:mimi-puppy] [--out DIR]
It starts its own sidecar on a spare port with a state folder of its own, holding only the
QualiTaTi sign-in, so nothing it does shows in the app or can reach mail or other accounts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from urllib.parse import quote

import websockets

REPO = Path(__file__).resolve().parent.parent if (Path(__file__).resolve().parent.parent / "coworker").is_dir() else Path.cwd()

NOTES = """Trust in remote teams: notes for a class

Swift trust: temporary teams act as if trust exists from day one, based on roles, then
confirm or withdraw it through early actions (Meyerson, Weick and Kramer 1996).
Two kinds of trust: cognitive (competence, reliability) and affective (care, concern).
Remote work builds cognitive trust at a normal pace but slows affective trust, because
informal contact is rare.
What is lost: hallway talk, seeing effort, quick repair after a misunderstanding.
What managers do wrong: monitor more. Monitoring signals distrust and lowers effort.
What works: predictable communication rhythms, visible work in progress, early small
deliverables, one in-person meeting at the start when possible.
A study of 1,400 engineers found teams that met once in person at kickoff reported
23 percent higher trust after six months than teams that never met.
Class exercise: students rate trust in a five-person remote project team at week 1 and
week 4 and explain the change.
"""

CASES = {
    # A topic and nothing else: the commonest way people ask.
    "topic": ("Make me a slide deck about how remote work changes trust in teams. It is for a "
              "20-minute MBA class session, about 8 slides. Save it as a PowerPoint file.", None),
    # Their own material: the deck must carry the notes' content, not general knowledge.
    "notes": ("Turn the attached notes into slides for my class. About 8 slides, PowerPoint.", NOTES),
    # Chinese, short, the way many users write.
    "chinese": ("帮我做一份PPT，主题是远程办公如何影响团队信任，给MBA学生上课用，8页左右。", None),
}

ANSWER = "Use your best judgment and go ahead. Do not ask me anything else."


def spare_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def own_state(folder: Path) -> None:
    """A state folder holding the QualiTaTi sign-in and nothing else."""
    from coworker.secrets import state_dir

    folder.mkdir(parents=True, exist_ok=True)
    saved = json.loads((state_dir() / "secrets.json").read_text())
    kept = {name: value for name, value in saved.items() if name in ("provider:qualitati", "qualitati:auth")}
    if "provider:qualitati" not in kept:
        raise SystemExit("No QualiTaTi sign-in on this computer: sign in to MimiWork first.")
    target = folder / "secrets.json"
    target.touch(mode=0o600)
    target.write_text(json.dumps(kept))
    (folder / "prefs.json").write_text(json.dumps({"onboarded": True, "language": "en", "tour_seen": True}))


async def ask(port: int, token: str, work: Path, model: str, text: str, notes: str | None, limit: float) -> dict:
    url = f"ws://127.0.0.1:{port}/ws/session/{uuid.uuid4().hex}?workspace={quote(str(work))}"
    tools: list[str] = []
    questions: list[str] = []
    errors: list[str] = []
    notices: list[str] = []
    said: list[str] = []
    log = (work.parent / f"{work.name}.events.jsonl").open("w")
    started = time.monotonic()
    first_tool = None
    async with websockets.connect(url, subprotocols=["openworker", token], max_size=None) as ws:
        async def send(frame: dict) -> None:
            await ws.send(json.dumps(frame))

        while json.loads(await ws.recv()).get("type") != "ready":
            pass
        await send({"type": "set_mode", "mode": "auto"})
        await send({"type": "set_model", "model": model})
        attachments = [{"kind": "text", "name": "notes.txt", "mime": "text/plain", "text": notes}] if notes else []
        started = time.monotonic()
        await send({"type": "user_message", "text": text, "attachments": attachments})
        while True:
            left = limit - (time.monotonic() - started)
            if left <= 0:
                errors.append(f"gave up after {limit:.0f} seconds")
                await send({"type": "interrupt", "force": True})
                break
            try:
                event = json.loads(await asyncio.wait_for(ws.recv(), timeout=left))
            except asyncio.TimeoutError:
                continue
            kind, data = event.get("type"), event.get("data") or {}
            if kind not in ("assistant_delta", "reasoning_delta", "tool_progress", "session_status", "activity"):
                log.write(json.dumps({"t": round(time.monotonic() - started, 1), **event}, ensure_ascii=False)[:20000] + "\n")
            if kind == "tool_started":
                first_tool = first_tool or time.monotonic() - started
                tools.append(str(data.get("name") or data.get("tool_name") or data.get("tool") or "?"))
            elif kind == "assistant_message":
                said.append(str(data.get("text") or data.get("content") or ""))
            elif kind == "question_requested":
                questions.append(str(data.get("question") or ""))
                await send({"type": "question_response", "answer": ANSWER})
            elif kind == "plan_proposed":
                await send({"type": "plan_response", "approved": True, "mode": "auto"})
            elif kind == "permission_required":
                await send({"type": "approval", "decision": "once"})
            elif kind == "directory_requested":
                await send({"type": "directory_response", "granted": False})
            elif kind == "notice":
                notices.append(str(data.get("text") or data.get("message") or data)[:200])
            elif kind in ("error", "input_rejected"):
                errors.append(str(data.get("error") or data.get("message") or data)[:400])
            elif kind == "turn_done":
                break
    log.close()
    return {
        "seconds": round(time.monotonic() - started),
        "first_tool_seconds": round(first_tool) if first_tool else None,
        "tool_calls": len(tools),
        "tools": dict(Counter(tools).most_common()),
        "questions": questions,
        "notices": notices,
        "errors": errors,
        "last_words": (said[-1] if said else "")[:1500],
    }


def pictures(deck: Path, into: Path) -> int:
    """Every slide as a PNG, through LibreOffice and the PDF it writes. 0 when it cannot."""
    office = shutil.which("soffice")
    if not office:
        return 0
    into.mkdir(parents=True, exist_ok=True)
    subprocess.run([office, "--headless", "--convert-to", "pdf", "--outdir", str(into), str(deck)],
                   capture_output=True, timeout=180, check=False)
    pdf = into / (deck.stem + ".pdf")
    if not pdf.exists():
        return 0
    import pypdfium2

    from coworker.tools.office.pdf_tools import render_pages

    document = pypdfium2.PdfDocument(str(pdf))
    count = len(document)
    document.close()
    for number, shot in enumerate(render_pages(pdf, list(range(1, count + 1)), into, "s"), 1):
        shot.rename(into / f"slide-{number:02d}.jpg")
    return count


def sheet(folder: Path, count: int) -> Path | None:
    """All slides on one picture, three across, so a deck is judged at a glance."""
    from PIL import Image

    shots = [Image.open(folder / f"slide-{n:02d}.jpg") for n in range(1, count + 1)]
    shots = [shot.resize((640, round(640 * shot.height / shot.width))) for shot in shots]
    if not shots:
        return None
    w, h = shots[0].size
    across = 3
    down = -(-len(shots) // across)
    page = Image.new("RGB", (across * w + (across + 1) * 8, down * h + (down + 1) * 8), "#888888")
    for index, shot in enumerate(shots):
        page.paste(shot.resize((w, h)), (8 + (index % across) * (w + 8), 8 + (index // across) * (h + 8)))
    target = folder / "sheet.jpg"
    page.save(target)
    return target


def deck_facts(deck: Path) -> dict:
    from pptx import Presentation

    slides = Presentation(str(deck)).slides
    words, with_picture, with_notes, empty = [], 0, 0, 0
    for slide in slides:
        text = " ".join(shape.text_frame.text for shape in slide.shapes if shape.has_text_frame)
        cjk = sum("\u4e00" <= ch <= "\u9fff" for ch in text)
        words.append(cjk if cjk > len(text) / 4 else len(text.split()))
        with_picture += any(shape.shape_type == 13 for shape in slide.shapes)
        with_notes += bool(slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip())
        empty += not text.strip()
    return {"slides": len(slides), "most_text_on_a_slide": max(words, default=0), "slides_with_a_picture": with_picture,
            "slides_with_notes": with_notes, "slides_with_no_text": empty}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("cases", nargs="*", default=list(CASES), help=f"which to run: {', '.join(CASES)}")
    parser.add_argument("--model", default="qualitati:mimi-puppy")
    parser.add_argument("--out", default="")
    parser.add_argument("--limit", type=float, default=1500, help="seconds before a run is given up")
    args = parser.parse_args()
    sys.path.insert(0, str(REPO))
    out = Path(args.out or Path.home() / ".cache" / "mimiwork-live" / time.strftime("%Y%m%d-%H%M%S")).resolve()
    state = out / "state"
    own_state(state)
    port = spare_port()
    env = {**os.environ, "COWORKER_STATE_DIR": str(state)}
    env.pop("COWORKER_API_TOKEN", None)
    server = subprocess.Popen([sys.executable, "-m", "coworker.server.run", "--port", str(port), "--cwd", str(out)],
                              cwd=REPO, env=env, stdout=(out / "server.log").open("w"), stderr=subprocess.STDOUT)
    try:
        token_file = state / f"sidecar-{port}.token"
        for _ in range(120):
            if token_file.exists():
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=1).close()
                    break
                except OSError:
                    pass
            time.sleep(0.5)
        else:
            raise SystemExit(f"The sidecar did not start; see {out / 'server.log'}")
        token = token_file.read_text().strip()

        async def one(name: str) -> dict:
            text, notes = CASES[name]
            work = out / f"{name}-{args.model.split(':')[-1]}"
            work.mkdir(parents=True, exist_ok=True)
            try:
                result = await ask(port, token, work, args.model, text, notes, args.limit)
            except Exception as reason:  # noqa: BLE001 - one broken run must not hide the others
                result = {"errors": [f"{type(reason).__name__}: {reason}"]}
            decks = sorted(work.rglob("*.pptx"), key=lambda p: p.stat().st_mtime)
            result.update(case=name, model=args.model, folder=str(work),
                          files=[str(p.relative_to(work)) for p in work.rglob("*") if p.is_file() and "shots" not in p.parts][:40])
            if decks:
                result["deck"] = str(decks[-1])
                try:
                    result.update(deck_facts(decks[-1]))
                    count = pictures(decks[-1], work / "shots")
                    made = sheet(work / "shots", count) if count else None
                    result["sheet"] = str(made) if made else None
                except Exception as reason:  # noqa: BLE001
                    result["errors"] = [*result.get("errors", []), f"reading the deck: {reason}"]
            else:
                result["errors"] = [*result.get("errors", []), "no PowerPoint file was made"]
            (work.parent / f"{work.name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
            return result

        results = await asyncio.gather(*(one(name) for name in args.cases))
    finally:
        server.terminate()
        # The sign-in copy is only needed while the sidecar runs.
        shutil.rmtree(state, ignore_errors=True)
    print(json.dumps(results, ensure_ascii=False, indent=1))
    return 1 if any(r.get("errors") for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
