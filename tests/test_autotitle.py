"""FB-010 — LLM auto-titles.

After a user turn completes, the manager fires ONE fire-and-forget completion on the
session's own provider/model to generate a 4-5 word title, stored in `auto_title` —
never in `title`, so a manual rename always wins. The small-talk sentinel earns exactly
one retry (with both openers) after the next user turn; every failure is swallowed."""

from __future__ import annotations

import asyncio
import time

from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient
from coworker.server.manager import SessionManager


class TitleAwareProvider(ProviderClient):
    """Chat turns come from one queue; title calls (recognized by the titling system
    prompt) are answered from another — so the fire-and-forget title call can never
    steal a scripted chat turn."""

    def __init__(self, chat_turns, titles):
        self._chat = list(chat_turns)
        self._titles = list(titles)
        self.title_calls: list[list[dict]] = []

    def complete(self, *, model, messages, tools=None, **settings):
        if messages and "title chat sessions" in str(messages[0].get("content", "")):
            self.title_calls.append([dict(m) for m in messages])
            item = self._titles.pop(0)
            if isinstance(item, Exception):
                raise item
            return AssistantTurn(text=item, finish_reason="stop")
        return self._chat.pop(0)

    def capabilities(self, model):
        return ModelCapabilities()


def _text(text):
    return AssistantTurn(text=text, finish_reason="stop")


async def _turn(
    mgr: SessionManager, sid: str, text: str, *, agent: str = "chat", workspace=None
) -> None:
    """Drive one user turn the way the server does: run, save, mark idle (the
    auto-title hook), then wait for the fire-and-forget call to settle."""
    engine = mgr.get_engine(
        sid, agent=agent, **({"workspace": str(workspace)} if workspace else {})
    )
    mgr.mark_running(sid)
    async for _ in engine.run(text):
        pass
    mgr.save(sid, engine)
    mgr.mark_idle(sid)
    deadline = time.time() + 5.0
    while sid in mgr._autotitle_inflight and time.time() < deadline:
        await asyncio.sleep(0.005)


def _mgr(tmp_path, chat_turns, titles):
    provider = TitleAwareProvider(chat_turns, titles)
    return SessionManager(workspace=tmp_path, provider=provider), provider


async def test_title_set_after_first_turn(tmp_path):
    mgr, provider = _mgr(tmp_path, [_text("sure")], ["Japan Trip Planning Help"])
    await _turn(mgr, "s1", "help me plan a trip to japan")

    assert len(provider.title_calls) == 1
    assert provider.title_calls[0][-1]["content"] == "help me plan a trip to japan"
    assert mgr.session_store.title_state("s1")["auto_title"] == (
        "Japan Trip Planning Help"
    )
    # display precedence: the auto title wins over the title_from snapshot everywhere
    assert mgr.session_store.load("s1").title == "Japan Trip Planning Help"
    row = next(s for s in mgr.list_sessions() if s["session_id"] == "s1")
    assert row["title"] == "Japan Trip Planning Help"


async def test_small_talk_sentinel_then_retry_with_both_openers(tmp_path):
    mgr, provider = _mgr(
        tmp_path,
        [_text("hey!"), _text("on it")],
        ["small-talk", "Quarterly Report Draft"],
    )
    await _turn(mgr, "s2", "hey")
    assert mgr.session_store.title_state("s2")["auto_title"] is None
    assert mgr.session_store.load("s2").title == "hey"  # title_from fallback stands

    await _turn(mgr, "s2", "help me draft the quarterly report")
    assert len(provider.title_calls) == 2
    retry_opener = provider.title_calls[1][-1]["content"]
    assert "hey" in retry_opener and "quarterly report" in retry_opener
    assert mgr.session_store.load("s2").title == "Quarterly Report Draft"


async def test_gives_up_after_second_sentinel(tmp_path):
    mgr, provider = _mgr(
        tmp_path,
        [_text("hi"), _text("hello"), _text("yo")],
        ["small-talk", "small-talk", "Should Never Be Asked"],
    )
    await _turn(mgr, "s3", "hey")
    await _turn(mgr, "s3", "how are you")
    await _turn(mgr, "s3", "good morning")
    assert len(provider.title_calls) == 2  # attempt 1 + the single retry, then give up
    assert mgr.session_store.title_state("s3")["auto_title"] is None
    assert mgr.session_store.load("s3").title == "hey"


async def test_manual_rename_always_wins(tmp_path):
    # rename AFTER the auto title landed
    mgr, _ = _mgr(tmp_path, [_text("ok")], ["Login Bug Investigation"])
    await _turn(mgr, "s4", "the login page 500s")
    assert mgr.session_store.load("s4").title == "Login Bug Investigation"
    mgr.rename_session("s4", "Prod incident 42")
    assert mgr.session_store.load("s4").title == "Prod incident 42"
    # ...and a late-landing generated title can't displace it
    assert mgr.session_store.set_auto_title("s4", "sneaky") is False
    assert mgr.session_store.load("s4").title == "Prod incident 42"


async def test_rename_before_generation_blocks_it(tmp_path):
    mgr, provider = _mgr(
        tmp_path, [_text("hi"), _text("ok")], ["small-talk", "Should Never Be Asked"]
    )
    await _turn(mgr, "s5", "hey")  # sentinel — no title yet
    mgr.rename_session("s5", "My Thread")
    await _turn(mgr, "s5", "help me plan the offsite")
    assert len(provider.title_calls) == 1  # the retry never fired
    assert mgr.session_store.load("s5").title == "My Thread"


async def test_provider_failure_is_swallowed(tmp_path):
    mgr, provider = _mgr(tmp_path, [_text("ok")], [RuntimeError("model down")])
    await _turn(mgr, "s6", "summarize this doc")  # must not raise
    assert mgr.session_store.title_state("s6")["auto_title"] is None
    assert mgr.session_store.load("s6").title == "summarize this doc"


async def test_sanitizes_and_rejects_absurd_output(tmp_path):
    # surrounding quotes stripped + whitespace collapsed
    mgr, _ = _mgr(tmp_path, [_text("ok")], ['"Fix   Login Bug"'])
    await _turn(mgr, "s7", "the login page 500s")
    assert mgr.session_store.load("s7").title == "Fix Login Bug"

    # absurdly long output (>80 chars) is a failure, not a title
    mgr2, _ = _mgr(tmp_path / "b", [_text("ok")], ["x" * 90])
    await _turn(mgr2, "s8", "the login page 500s")
    assert mgr2.session_store.title_state("s8")["auto_title"] is None


# ── re-titling from what the session produced (owner ask 2026-08-31) ──────────


async def test_a_long_session_is_retitled_from_what_it_became(tmp_path):
    """Titling from the opening alone means a conversation that starts "help me with
    this" is named after the vague part for ever, however much work followed. Once the
    session has a subject, the title comes from it."""
    mgr, provider = _mgr(
        tmp_path,
        [_text("on it"), _text("b"), _text("c"), _text("the churn is in month two")],
        ["Help With This Thing", "Month Two Churn"],
    )
    await _turn(mgr, "s1", "help me with this")
    assert mgr.session_store.title_state("s1")["auto_title"] == "Help With This Thing"

    for text in ("keep going", "and then", "summarise it"):
        await _turn(mgr, "s1", text)

    assert mgr.session_store.title_state("s1")["auto_title"] == "Month Two Churn"
    last = provider.title_calls[-1]
    # The re-title was given what the session SAID, not only how it opened.
    assert "churn is in month two" in last[-1]["content"]
    assert "produce" in str(last[0]["content"]).lower()


async def test_the_retitle_is_given_the_files_the_session_produced(tmp_path):
    """Files are the strongest signal of what a session was about, and they trigger the
    re-title on their own — without waiting for the conversation to get long."""
    mgr, provider = _mgr(
        tmp_path, [_text("on it"), _text("done")], ["Help With This", "Q3 Churn Analysis"]
    )
    await _turn(mgr, "s1", "help me with this")

    # Stand in for the artifact tracker: what matters here is that produced files reach
    # the titling call, not how the tracker decides a file was produced.
    mgr.list_artifacts = lambda _sid: [{"name": "Q3 churn analysis.docx"}]  # type: ignore[method-assign]
    await _turn(mgr, "s1", "write it up")

    assert mgr.session_store.title_state("s1")["auto_title"] == "Q3 Churn Analysis"
    assert "Q3 churn analysis.docx" in provider.title_calls[-1][-1]["content"]


async def test_the_retitle_happens_once_not_on_every_turn(tmp_path):
    """A title the user has grown used to must not keep moving under them."""
    mgr, provider = _mgr(
        tmp_path,
        [_text("a"), _text("b"), _text("c")],
        ["First Title Here", "Second Title Here"],
    )
    await _turn(mgr, "s1", "help me with this")
    mgr.list_artifacts = lambda _sid: [{"name": "report.docx"}]  # type: ignore[method-assign]

    await _turn(mgr, "s1", "keep going")
    await _turn(mgr, "s1", "and again")

    assert len(provider.title_calls) == 2, "the title was regenerated more than once"
    assert mgr.session_store.title_state("s1")["auto_title"] == "Second Title Here"


async def test_a_manual_rename_survives_the_content_pass(tmp_path):
    """The one thing re-titling must never do."""
    mgr, _ = _mgr(tmp_path, [_text("a"), _text("b")], ["Auto One", "Auto Two"])
    await _turn(mgr, "s1", "help me with this")
    mgr.rename_session("s1", "My own name")

    mgr.list_artifacts = lambda _sid: [{"name": "report.docx"}]  # type: ignore[method-assign]
    await _turn(mgr, "s1", "carry on")

    assert mgr.session_store.load("s1").title == "My own name"


async def test_nothing_produced_and_barely_started_keeps_its_opening_title(tmp_path):
    """A short chat that made nothing has no better name available — asking the model
    again would just spend a call to get the same answer back."""
    mgr, provider = _mgr(tmp_path, [_text("a"), _text("b")], ["Opening Title Here"])
    await _turn(mgr, "s1", "what is a p value")
    await _turn(mgr, "s1", "thanks")

    assert len(provider.title_calls) == 1
    assert mgr.session_store.title_state("s1")["auto_title"] == "Opening Title Here"
