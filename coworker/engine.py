"""TurnEngine — the owned agent loop.

Async, but with blocking provider/tool calls wrapped in `asyncio.to_thread` so the loop
(and any UI consuming its events) stays responsive. One user turn spans many model↔tool
iterations until the model stops requesting tools, a rail trips, or it's interrupted.
When the model requests several tool calls in one turn, low-risk ones (reads, searches)
execute concurrently; writes/shell stay strictly ordered.

Approvals are handled out-of-band via an injected async `approver`: when the permission
engine says `needs_user`, the engine emits `PERMISSION_REQUIRED` and awaits the approver.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from . import compaction as _compaction
from . import repetition as _repetition
from .events import Event, EventType
from .fivea import classify_turn
from .permissions import Mode, PermissionEngine
from .providers import AssistantTurn, ProviderClient, ToolCall
from .providers.errors import (
    friendly_model_error,
    friendly_transient_error,
    is_transient,
    retry_after_seconds,
)
from .repetition import RepetitionGuard as _RepetitionGuard
from .timesaved import TimeSaved
from .tools import RecoveryPolicy, ToolRegistry


class ApprovalOutcome(str, Enum):
    ONCE = "once"
    ALWAYS_TOOL = "always_tool"
    ALWAYS_COMMAND = "always_command"
    DENY = "deny"


@dataclass
class PermissionRequest:
    tool_name: str
    arguments: dict[str, Any]
    metadata: Any
    reason: str
    tool_call_id: Optional[str] = None  # for durable resume (idempotent inbox item)


Approver = Callable[[PermissionRequest], Awaitable[ApprovalOutcome]]


_WRAP_UP_TEXT = (
    "You are almost out of tool steps for this turn. Finish now: write the deliverable "
    "with what you already have, then reply with a short summary of what is done and what "
    "is still missing. Do not start new research."
)


@dataclass
class ToolHooks:
    """Plugin-style tool hooks (opencode hooks, minimal form). ``pre`` hooks run before
    execution and may short-circuit it by returning a non-None result; ``post`` hooks run
    after with the result + status. Attached post-construction as ``engine.hooks`` (None
    by default, so engines without hooks behave identically)."""

    pre: list[Callable[[str, dict[str, Any]], Any]] = field(default_factory=list)
    post: list[Callable[[str, dict[str, Any], Any, str], None]] = field(
        default_factory=list
    )


async def _deny_all(_request: PermissionRequest) -> ApprovalOutcome:
    return ApprovalOutcome.DENY


class TurnEngine:
    def __init__(
        self,
        *,
        provider: ProviderClient,
        registry: ToolRegistry,
        permissions: PermissionEngine,
        model: str,
        instructions: Optional[str] = None,
        approver: Optional[Approver] = None,
        max_iterations: int = 12,
        model_settings: Optional[dict[str, Any]] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        audit_sink: Optional[Callable[[dict[str, Any]], None]] = None,
        context_provider: Optional[Callable[[], str]] = None,
        directory_requester: Optional[
            Callable[[dict[str, Any]], "Awaitable[dict[str, Any]]"]
        ] = None,
        plan_approver: Optional[
            Callable[[dict[str, Any]], "Awaitable[dict[str, Any]]"]
        ] = None,
        question_asker: Optional[
            Callable[[dict[str, Any]], "Awaitable[dict[str, Any]]"]
        ] = None,
        # Called (thread-safe, best-effort) when the user stops the turn — e.g. the
        # executor's kill for a running shell command.
        interrupt_hooks: Optional[list[Callable[[], None]]] = None,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.permissions = permissions
        self.model = model
        self.approver = approver or _deny_all
        self.max_iterations = max_iterations
        self.model_settings = dict(model_settings or {})
        self.messages: list[dict[str, Any]] = list(messages or [])
        self.audit_sink = audit_sink
        # Returns an ephemeral `<system-context>` block appended to the LAST user message at
        # send-time only (never persisted). We can't reliably inject system messages mid-thread
        # across providers, so dynamic per-turn context (e.g. the live directory list) rides on
        # the latest user turn. Returns "" when there's nothing to add.
        self.context_provider = context_provider
        # Handles the `request_directory` tool: emits a DIRECTORY_REQUESTED prompt, waits for the
        # user to grant/decline a folder out-of-band, applies the grant to this live session, and
        # returns the outcome. None on surfaces that can't prompt (the tool then no-ops).
        self.directory_requester = directory_requester
        # Handles the `propose_plan` tool: emits PLAN_PROPOSED, waits for the user's decision.
        # An approving result flips the live PermissionEngine out of plan mode (same session,
        # context kept). None on surfaces that can't prompt (the tool then no-ops).
        self.plan_approver = plan_approver
        # Handles the `ask_user` tool: turns a question into an Inbox item and waits for the answer
        # (answerable inline in a live session or from the Inbox when unattended). None on surfaces
        # that can't ask (the tool then no-ops).
        self.question_asker = question_asker
        # Plugin-style tool hooks (ToolHooks). Attached post-construction like `spill`
        # (see build_engine); None keeps old behaviour byte-identical.
        self.hooks: Optional[ToolHooks] = None
        # Transient provider failures (429/5xx/timeouts) are retried with these delays
        # before the turn surfaces an error — only when nothing has streamed yet, so the
        # user never sees duplicated text. Tests shrink the delays to zero.
        self.retry_delays: tuple[float, ...] = (1.0, 3.0, 8.0, 15.0, 30.0, 30.0)
        self._wrap_up_sent = False
        # Auto-compaction (OPE-27) — set post-construction by the surface/manager so the
        # constructor footprint stays put. `compaction_settings` is a live getter (Settings
        # changes apply without a rebuild); `is_attended` gates the failure prompt (None →
        # treat as unattended: never park a background run on internal bookkeeping).
        self.compaction_state: Optional[_compaction.CompactionState] = None
        self.compaction_settings: Optional[Callable[[], dict[str, Any]]] = None
        self.is_attended: Optional[Callable[[], bool]] = None
        # Oversized tool output → a file in the workspace + a head/tail summary. Attached
        # post-construction like the compaction hooks above; None keeps results verbatim.
        self.spill: Optional[Any] = None
        self._last_context_tokens: Optional[int] = None
        self.audit_context: dict[str, Any] = {}
        # What this turn would have cost by hand, minus what it cost with Mimi.
        # Accumulated from real tool results (see timesaved.py) and reset each turn.
        self.time_saved = TimeSaved()
        # Five A's (ch. 7): a turn is placed by BEHAVIOUR, so the engine records what
        # it actually reached for — tool names and their categories — and the rung is
        # decided at the end. Counts live beside the time totals and travel with them.
        self.five_a: dict[str, int] = {}
        # Memory consolidation (see _queue_memory_consolidation): asked once, at the
        # first compaction. `memory_enabled` is set by the builder — false when the
        # user turned saving off, so the nudge stays quiet rather than inviting a bluff.
        self._memory_nudged = False
        # Fail closed: an engine built without a memory store must never be asked to
        # save. The builder turns this on when there is a store AND saving is enabled.
        self.memory_enabled = False
        self._turn_tools: set[str] = set()
        # Set by the surface when an automation started the turn, or a plan was approved.
        self.turn_scheduled = False
        self._turn_planned = False
        self._turn_started = 0.0
        self._turn_approvals = 0
        if instructions and not (
            self.messages and self.messages[0].get("role") == "system"
        ):
            self.messages.insert(0, {"role": "system", "content": instructions})
        self._cancel = asyncio.Event()
        # Each pending steering message: (text, optional MessageSource sidecar dict).
        self._steering: list[tuple[str, Optional[dict[str, Any]]]] = []
        # tool_call.id → the standing rule that auto-allowed it ("tool → target"), so the
        # TOOL_FINISHED event can carry the note to the tool card (§25).
        self._standing_notes: dict[str, str] = {}
        self._interrupt_hooks: list[Callable[[], None]] = list(interrupt_hooks or [])
        # Surfaces that persist sessions attach these post-construction.  Keeping the
        # core engine optional preserves lightweight/direct use, while the desktop and
        # automation paths get one shared crash-recovery boundary.
        self.tool_journal: Optional[Any] = None
        # Persistent engines attach a RecoverySession. It snapshots managed file targets
        # before execution, so the Files panel can restore the whole user turn.
        self.file_recovery: Optional[Any] = None
        self.session_id = ""
        self.checkpoint: Optional[Callable[[], None]] = None
        self._resuming = False
        self._resume_prepared_call_ids: set[str] = set()

    # -- external controls ------------------------------------------------------
    def request_interrupt(self) -> None:
        """Stop the turn as soon as possible, from ANY state: mid-stream (the producer
        thread drops the stream between chunks), mid-tool (interrupt hooks kill the
        running command), awaiting an approval/question/plan (the await resolves as
        interrupted), or between iterations (the loop checkpoint). Every pending
        tool_call still gets a tool-error result so the history never carries orphans
        (hosted templates reject them, and durable-resume would re-prompt them)."""
        self._cancel.set()
        for hook in self._interrupt_hooks:
            try:
                hook()
            except Exception:
                pass  # best-effort: a dead executor must not block the stop

    async def _interruptible(self, coro: Any, interrupted: Any) -> Any:
        """Await `coro`, but resolve early with `interrupted` if the user stops the
        turn. The pending task is cancelled so an answered-later Inbox card no-ops."""
        task = asyncio.ensure_future(coro)
        cancel_wait = asyncio.ensure_future(self._cancel.wait())
        try:
            done, _ = await asyncio.wait(
                {task, cancel_wait}, return_when=asyncio.FIRST_COMPLETED
            )
            if task in done:
                return task.result()
            task.cancel()
            return interrupted
        finally:
            cancel_wait.cancel()

    def queue_steering(
        self, text: str, source: Optional[dict[str, Any]] = None
    ) -> None:
        self._steering.append((text, source))

    def seed_approved_recovery(self, tool_call_id: str) -> None:
        """Mark a legacy call as prepared when a durable approval proves it never ran."""
        if tool_call_id:
            self._resume_prepared_call_ids.add(tool_call_id)

    # -- main loop --------------------------------------------------------------
    async def run(
        self,
        user_input: "str | list",
        *,
        source: Optional[dict[str, Any]] = None,
        display: Optional[str] = None,
    ) -> AsyncIterator[Event]:
        # `user_input` is a string, or OpenAI content-parts (text + image_url) for attachments.
        # `source` (a MessageSource dict) is a display-only sidecar for connector messages: it
        # rides on the persisted user message + the TURN_START event, but is stripped before the
        # message reaches a provider (see `_outbound_messages`). `content` stays the framed text.
        # `display` is the same split for force-run skills (SKILLS-SPEC §4.1 #3): the user's
        # literal "/skill …" line for the transcript, while `content` carries the model-facing
        # framing. `ts` (unix seconds, stamped on every appended message) is the same kind of
        # sidecar.
        message: dict[str, Any] = {
            "role": "user",
            "content": user_input,
            "ts": time.time(),
        }
        if source is not None:
            message["source"] = source
        if display is not None:
            message["_display"] = display
        self.messages.append(message)
        self._cancel.clear()
        data: dict[str, Any] = {"input": user_input}
        if source is not None:
            data["source"] = source
        if display is not None:
            data["display"] = display
        self._begin_turn()
        yield Event(EventType.TURN_START, data)
        async for event in self._loop():
            yield event

    def switch_model(self, model: str) -> Optional[str]:
        """Rebind the session's model mid-conversation (roadmap item 3). History is
        canonical OpenAI shape and every provider converts per call, so the switch is just
        the field write — plus a persisted notice marking WHERE it happened, with a
        degradation warning when history carries images the new model can't see (those are
        sent as placeholders — see `_outbound_messages`). Returns the notice text, or None
        when nothing changed (same model, or first bind on a fresh session)."""
        if not model or model == self.model:
            return None
        had_history = any(m.get("role") != "system" for m in self.messages)
        self.model = model
        if not had_history:
            return None
        from .providers.matrix import model_labels

        text = f"Model switched to {model_labels().get(model, model)}"
        try:
            caps = self.provider.capabilities(model)
        except Exception:
            caps = None
        if (
            caps is not None
            and not getattr(caps, "vision", False)
            and self._history_has_images()
        ):
            text += " — earlier images can't be read by this model"
        self._append_notice("model_switch", text)
        return text

    def _history_has_images(self) -> bool:
        return any(
            isinstance(p, dict) and p.get("type") == "image_url"
            for msg in self.messages
            if isinstance(msg.get("content"), list)
            for p in msg["content"]
        )

    def _tail_is_retriable_error(self) -> bool:
        """True when the history tail is an error notice, looking through any model_switch
        notices appended after it (a switch must not consume the retry)."""
        for message in reversed(self.messages):
            if message.get("role") != "notice":
                return False
            if message.get("kind") == "model_switch":
                continue
            return message.get("kind") == "error"
        return False

    def _append_notice(self, kind: str, text: Optional[str] = None) -> None:
        """Persist a turn-ending marker (error/interrupted) as a display-only `notice`
        message: it survives reload like the transcript does, but `_outbound_messages`
        drops the role so no provider ever sees it."""
        notice: dict[str, Any] = {"role": "notice", "kind": kind, "ts": time.time()}
        if text:
            notice["text"] = text
        self.messages.append(notice)

    async def retry(self) -> AsyncIterator[Event]:
        """Re-run the model loop after a provider error — no new user message; the failed
        turn's input is already the tail of history. Guarded on the tail being an error
        notice so a stray retry frame can't re-answer a completed turn. Trailing
        model_switch notices don't break the guard — switching models and THEN retrying
        is the intended recovery path (owner-hit 2026-07-23)."""
        if not self._tail_is_retriable_error():
            return
        self._cancel.clear()
        self._begin_turn()
        yield Event(EventType.TURN_START, {"input": ""})
        async for event in self._loop():
            yield event

    async def resume(self) -> AsyncIterator[Event]:
        """Continue a turn that was suspended at a prompt and persisted — durable resume after a
        restart (or engine eviction). Re-process the trailing assistant message's UNANSWERED
        tool-calls (the prompt callbacks find the already-resolved Inbox item and return without
        re-prompting; answered calls are skipped, so nothing double-executes), then run the model
        loop to finish the turn."""
        pending = self._unanswered_trailing_tool_calls()
        if not pending:
            return
        self._cancel.clear()
        self._begin_turn()
        yield Event(EventType.TURN_START, {"input": "(resumed)"})
        self._resuming = True
        try:
            async for event in self._handle_tool_calls(pending):
                yield event
        finally:
            self._resuming = False
        yield Event(EventType.ITERATION_END, {"iteration": 0})
        if not self._cancel.is_set():
            async for event in self._loop():
                yield event

    def _unanswered_trailing_tool_calls(self) -> list[ToolCall]:
        """The tool-calls of the last assistant message that don't yet have a tool result —
        i.e. the prompt we suspended on (+ any after it). Reconstructed from the persisted thread.
        """
        for message_index in range(len(self.messages) - 1, -1, -1):
            msg = self.messages[message_index]
            if msg.get("role") == "user":
                return []
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                # Provider call IDs are only scoped to one assistant message.  Some
                # providers reuse them in later turns, so results from older turns must
                # not make a newer unanswered call look complete.
                answered = {
                    m.get("tool_call_id")
                    for m in self.messages[message_index + 1 :]
                    if m.get("role") == "tool"
                }
                out: list[ToolCall] = []
                for tc in msg["tool_calls"]:
                    if tc.get("id") in answered:
                        continue
                    fn = tc.get("function") or {}
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except Exception:
                        args = {}
                    out.append(
                        ToolCall(id=tc.get("id"), name=fn.get("name"), arguments=args)
                    )
                return out
        return []

    async def _loop(self) -> AsyncIterator[Event]:
        iterations = 0
        retries_used = 0
        # Fresh per turn: a stuck model re-sends near-identical iterations, and each
        # lap costs the user credits (see coworker/repetition.py, adapted from
        # FrontierAgent). Hint first, stop if it persists.
        # min_chars is low because the signature is structured (text + tool name +
        # args): "read_file {'path': 'a.txt'}" repeated six times is a loop even
        # though it's short. The class default (40) targets plain prose.
        rep_guard = _RepetitionGuard(min_chars=16)
        while True:
            if iterations >= self.max_iterations:
                yield Event(
                    EventType.TURN_END,
                    {**{"status": "max_iterations_exceeded", "iterations": iterations}, "time_saved": self._close_turn()},
                )
                return
            iterations += 1
            if (
                iterations == self.max_iterations
                and self.max_iterations > 2
                and not self._wrap_up_sent
            ):
                # Last allowed model call: steer it to land the deliverable instead of
                # starting more tool work and dying with max_iterations_exceeded.
                self._wrap_up_sent = True
                self.messages.append(
                    {
                        "role": "user",
                        "content": _WRAP_UP_TEXT,
                        "ts": time.time(),
                        "steering": "wrap_up",
                    }
                )
                yield Event(
                    EventType.NOTICE,
                    {"kind": "wrap_up", "text": "Almost out of steps — asking Mimi to wrap up."},
                )

            # Auto-compaction checkpoint (OPE-27): between tool turns and before a new
            # turn's first call. Deliberately no "wrap up" warning to the model. The
            # COMPACTING signal precedes the (multi-second) summarizer call so surfaces
            # can show progress instead of a silent stall.
            notice = None
            if self._compaction_due():
                yield Event(EventType.COMPACTING, {})
                notice = await self._compact_now()
            if notice:
                self._append_notice("compacted", notice)
                yield Event(EventType.COMPACTED, {"text": notice})

            turn: Optional[AssistantTurn] = None
            streamed: list[str] = []
            streamed_reasoning: list[str] = []

            def _partial_turn() -> AssistantTurn:
                # What the user watched arrive — text and thinking, NO tool calls (any
                # half-formed calls would either orphan or execute against the stop).
                return AssistantTurn(
                    text="".join(streamed) or None,
                    reasoning="".join(streamed_reasoning) or None,
                )

            try:
                async for chunk in self._astream():
                    if chunk.reasoning_delta:
                        streamed_reasoning.append(chunk.reasoning_delta)
                        yield Event(
                            EventType.REASONING_DELTA, {"text": chunk.reasoning_delta}
                        )
                    if chunk.text_delta:
                        streamed.append(chunk.text_delta)
                        yield Event(
                            EventType.ASSISTANT_DELTA, {"text": chunk.text_delta}
                        )
                    if chunk.turn is not None:
                        turn = chunk.turn
            except Exception as exc:  # provider failure
                # Momentary failure (rate limit, overload, network blip) with nothing
                # streamed yet: wait and call again — the user sees a quiet "retrying"
                # line, not a dead turn. Quota/auth/overflow errors never take this path.
                if (
                    is_transient(exc)
                    and not streamed
                    and not streamed_reasoning
                    and retries_used < len(self.retry_delays)
                    and not self._cancel.is_set()
                ):
                    delay = retry_after_seconds(exc) or self.retry_delays[retries_used]
                    retries_used += 1
                    yield Event(
                        EventType.NOTICE,
                        {
                            "kind": "retry",
                            "text": f"Model busy — retrying ({retries_used}/{len(self.retry_delays)})…",
                            "attempt": retries_used,
                            "delay": delay,
                        },
                    )
                    await asyncio.sleep(delay)
                    iterations -= 1  # the retry is the same step, not a new one
                    continue
                # A raw context-overflow 400 (compaction mispredicted, e.g. the estimate
                # path) routes into the compaction policy instead of surfacing. The retry
                # is progress-guarded: each pass moves the boundary forward or gives up,
                # so a model that keeps overflowing still terminates in the error path.
                if _compaction.is_context_overflow(exc) and not self._cancel.is_set():
                    yield Event(EventType.COMPACTING, {})
                    notice = await self._compact_now(force=True)
                    if notice:
                        self._append_notice("compacted", notice)
                        yield Event(EventType.COMPACTED, {"text": notice})
                        continue
                # Same contract as the stop path below: the partial the user watched
                # arrive survives the failure.
                if streamed or streamed_reasoning:
                    self.messages.append(_assistant_message(_partial_turn()))
                friendly = friendly_model_error(
                    self.model, exc
                ) or friendly_transient_error(exc)
                payload = {
                    "error": friendly or str(exc),
                    "error_type": type(exc).__name__,
                }
                if friendly:
                    payload["raw"] = str(exc)
                self._append_notice("error", friendly or str(exc))
                yield Event(EventType.ERROR, payload)
                return
            if self._cancel.is_set() and turn is None:
                # Stopped mid-stream: persist exactly what the user watched arrive.
                if streamed or streamed_reasoning:
                    self.messages.append(_assistant_message(_partial_turn()))
                self._append_notice("interrupted")
                yield Event(EventType.INTERRUPTED, {"iterations": iterations})
                return
            if turn is None:
                turn = AssistantTurn()
            retries_used = 0  # a successful call resets the transient-retry budget
            if turn.usage is not None:
                # The trigger signal: the prompt-side total that actually occupied the
                # window on this round-trip (estimate fallback when never reported).
                self._last_context_tokens = turn.usage.context_tokens

            self.messages.append(_assistant_message(turn, model=self.model))
            if turn.tool_calls and self.checkpoint is not None:
                # Persist the assistant's intent before any tool can cross the side-
                # effect boundary.  Without this checkpoint a journal row could outlive
                # the transcript entry needed to reconstruct it.
                try:
                    await asyncio.to_thread(self.checkpoint)
                except Exception as exc:
                    text = f"could not durably checkpoint tool calls: {exc}"
                    self._append_notice("error", text)
                    yield Event(
                        EventType.ERROR,
                        {"error": text, "error_type": "CheckpointError"},
                    )
                    return
            # Prepare every ordinary call before the assistant message is exposed
            # to a surface.  This removes the await/broadcast window between durable
            # intent and the first visible tool event.
            for tool_call in turn.tool_calls:
                if tool_call.name not in {
                    "request_directory",
                    "propose_plan",
                    "ask_user",
                }:
                    self._prepare_tool_recovery(tool_call)
            payload: dict[str, Any] = {
                "text": turn.text,
                "tool_calls": [tc.name for tc in turn.tool_calls],
            }
            if turn.reasoning:
                payload["reasoning"] = turn.reasoning
            if turn.usage is not None:
                payload["usage"] = {"model": self.model, **turn.usage.as_dict()}
            yield Event(EventType.ASSISTANT_MESSAGE, payload)

            if not turn.tool_calls:
                if self._steering:
                    self._inject_steering()
                    continue
                yield Event(
                    EventType.TURN_END,
                    {**{"status": "completed", "iterations": iterations}, "time_saved": self._close_turn()},
                )
                return

            # Repetition check BEFORE the tools run: when the verdict is "stop", the
            # identical lap is skipped, not executed one more time.
            signature = " ".join(
                [turn.text or ""]
                + [f"{tc.name} {json.dumps(tc.arguments, sort_keys=True)}" for tc in turn.tool_calls]
            )
            verdict = rep_guard.observe(signature)
            if verdict == "stop":
                self._append_notice(
                    "error", "Stopped: the model kept repeating the same step without progress."
                )
                yield Event(
                    EventType.NOTICE,
                    {
                        "kind": "repetition",
                        "text": "Mimi kept repeating the same step — stopping this turn.",
                    },
                )
                yield Event(
                    EventType.TURN_END,
                    {**{"status": "repetition_stop", "iterations": iterations}, "time_saved": self._close_turn()},
                )
                return
            if verdict == "hint":
                self.messages.append(
                    {
                        "role": "user",
                        "content": _repetition.HINT,
                        "ts": time.time(),
                        "steering": "repetition",
                    }
                )
                yield Event(
                    EventType.NOTICE,
                    {"kind": "repetition", "text": "Mimi seems to be looping — nudging it to change course."},
                )

            async for event in self._handle_tool_calls(turn.tool_calls):
                yield event

            yield Event(EventType.ITERATION_END, {"iteration": iterations})

            if self._cancel.is_set():
                self._append_notice("interrupted")
                yield Event(EventType.INTERRUPTED, {"iterations": iterations})
                return
            if self._steering:
                self._inject_steering()

    # -- auto-compaction (OPE-27) ------------------------------------------------
    def _queue_memory_consolidation(self) -> None:
        """Ask, once per session, for anything durable to be saved before it is lost.

        Once, not per compaction: a long session compacts repeatedly, and repeating the
        prompt would spend a turn each time and train the model to ignore it. Silent
        when memory is switched off — with no write tools the nudge would only invite
        the bluffing the off-notice exists to prevent.
        """
        if self._memory_nudged or not self.memory_enabled:
            return
        self._memory_nudged = True
        from .agent import MEMORY_CONSOLIDATION_NUDGE

        self.queue_steering(MEMORY_CONSOLIDATION_NUDGE, {"kind": "memory_consolidation"})

    def _compaction_config(self) -> dict[str, Any]:
        cfg = dict(self.compaction_settings() or {}) if self.compaction_settings else {}
        if not cfg.get("context_window"):
            from .providers.matrix import model_context_windows

            cfg["context_window"] = model_context_windows().get(self.model)
        cfg.setdefault("threshold_pct", _compaction.DEFAULT_THRESHOLD_PCT)
        cfg.setdefault("cap_tokens", _compaction.DEFAULT_CAP_TOKENS)
        return cfg

    def _compaction_due(self) -> bool:
        """The trigger check alone — cheap and side-effect free, so the loop can emit
        the COMPACTING signal before committing to the (slow) summarizer call."""
        cfg = self._compaction_config()
        if cfg.get("enabled") is False:
            return False
        signal = self._last_context_tokens or _compaction.estimate_tokens(
            self._outbound_messages()
        )
        return _compaction.should_compact(
            signal,
            cfg.get("context_window"),
            threshold_pct=float(cfg["threshold_pct"]),
            cap_tokens=int(cfg["cap_tokens"]),
        )

    async def _compact_now(self, *, force: bool = False) -> Optional[str]:
        """Run the compaction policy. Callers gate on `_compaction_due()` (or `force`,
        the overflow path). Returns the user-facing notice text when the outbound view
        changed, else None. Failure policy per spec: retry once (both modes); attended →
        Retry / Trim prompt; unattended → auto-trim and continue (never park a run on
        bookkeeping)."""
        cfg = self._compaction_config()
        pct = float(cfg["threshold_pct"])
        cap = int(cfg["cap_tokens"])
        window = cfg.get("context_window")
        keep = int(
            _compaction.KEEP_RECENT_FRACTION
            * _compaction.trigger_tokens(window, threshold_pct=pct, cap_tokens=cap)
        )
        model = str(cfg.get("model") or "") or self.model

        def _build() -> Optional[_compaction.CompactionState]:
            return _compaction.build_state(
                self.messages,
                provider=self.provider,
                model=model,
                keep_tokens=keep,
                prior=self.compaction_state,
            )

        state: Optional[_compaction.CompactionState] = None
        failed = False
        for _attempt in range(2):  # first try + the unconditional single retry
            try:
                state = await asyncio.to_thread(_build)
                failed = False
                break
            except Exception:
                failed = True
        if failed and self.question_asker is not None and self.is_attended and self.is_attended():
            while True:
                answer = await self._interruptible(
                    self.question_asker(
                        {
                            "question": (
                                "Context compaction failed — the summarizer couldn't "
                                "condense this session's history. How should I proceed?"
                            ),
                            "options": ["Retry", "Trim oldest 10%"],
                            "allow_text": False,
                            "header": "Compaction",
                        },
                        None,
                    ),
                    interrupted=None,
                )
                if not answer or answer.get("answer") != "Retry":
                    break
                try:
                    state = await asyncio.to_thread(_build)
                    failed = False
                    break
                except Exception:
                    continue
        if state is not None:
            self.compaction_state = state
            self._last_context_tokens = None  # stale once the outbound view shrank
            # The one moment where "save it now or lose it" is literally true: the
            # detail this conversation is built on is about to be summarised away.
            # Queued as steering so it lands at the next safe step and uses the
            # ordinary tools — the save notice and Undo still apply, and nothing is
            # written without the user seeing it.
            self._queue_memory_consolidation()
            return "Context compacted — earlier turns were summarized"
        if failed or force:
            trimmed = _compaction.trim_state(self.messages, prior=self.compaction_state)
            if trimmed is not None:
                self.compaction_state = trimmed
                self._last_context_tokens = None
                return "Context trimmed — oldest turns dropped (summary unavailable)"
        return None

    # -- helpers ----------------------------------------------------------------
    async def _astream(self):
        """Bridge the provider's blocking stream generator to the async loop via a
        thread + queue, so text deltas surface live without blocking the event loop."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        tools = self.registry.schemas() or None
        model, messages, settings = (
            self.model,
            self._outbound_messages(),
            self.model_settings,
        )
        provider = self.provider

        def produce():
            try:
                for chunk in provider.stream(
                    model=model, messages=messages, tools=tools, **settings
                ):
                    # User pressed Stop: drop the stream between chunks (reading the
                    # asyncio.Event's flag from a thread is safe; we only read).
                    if self._cancel.is_set():
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, ("chunk", chunk))
            except Exception as exc:  # surfaced to the awaiting consumer
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

        loop.run_in_executor(None, produce)
        while True:
            # Race the queue against Stop so a stalled stream (no chunks arriving —
            # the pre-first-token wait, a wedged connection) can't hold the turn.
            get_task = asyncio.ensure_future(queue.get())
            cancel_task = asyncio.ensure_future(self._cancel.wait())
            done, _ = await asyncio.wait(
                {get_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
            )
            cancel_task.cancel()
            if get_task not in done:
                get_task.cancel()
                return  # interrupted — the producer exits on its own next chunk
            kind, payload = get_task.result()
            if kind == "chunk":
                yield payload
            elif kind == "error":
                raise payload
            else:
                return

    @staticmethod
    def _arguments_hash(arguments: dict[str, Any]) -> str:
        encoded = json.dumps(
            arguments or {}, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _tool_run_position(self, tool_call: ToolCall) -> Optional[tuple[int, int]]:
        """Stable journal identity: persisted assistant-message index + call ordinal.

        Provider call IDs are retained for diagnostics but cannot be the key because
        they may be reused across turns.
        """
        expected_hash = self._arguments_hash(tool_call.arguments)
        for message_index in range(len(self.messages) - 1, -1, -1):
            message = self.messages[message_index]
            if message.get("role") != "assistant":
                continue
            for ordinal, raw in enumerate(message.get("tool_calls") or []):
                fn = raw.get("function") or {}
                if raw.get("id") != tool_call.id or fn.get("name") != tool_call.name:
                    continue
                try:
                    arguments = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    arguments = {}
                if self._arguments_hash(arguments) == expected_hash:
                    return message_index, ordinal
        return None

    def _prepare_tool_recovery(self, tool_call: ToolCall) -> dict[str, Any]:
        """Return ``proceed``, ``restore``, or ``indeterminate`` for this call.

        Every journal write is committed before execution.  A journal failure is a
        safety failure: the tool is not run.
        """
        journal = self.tool_journal
        if journal is None or not self.session_id:
            return {"action": "proceed", "key": None}
        position = self._tool_run_position(tool_call)
        if position is None:
            return {
                "action": "indeterminate",
                "reason": "could not identify the durable tool call; it was not executed",
                "key": None,
            }
        message_index, ordinal = position
        key = (message_index, ordinal)
        spec = self.registry.get(tool_call.name)
        policy = (
            spec.recovery_policy
            if spec is not None
            else RecoveryPolicy.NON_REPLAYABLE
        )
        arguments_hash = self._arguments_hash(tool_call.arguments)
        try:
            record = journal.get_tool_run(
                self.session_id, message_index, ordinal
            )
            legacy_ambiguous = (
                record is None
                and self._resuming
                and policy is RecoveryPolicy.NON_REPLAYABLE
                and tool_call.id not in self._resume_prepared_call_ids
            )
            if record is None:
                record = journal.prepare_tool_run(
                    self.session_id,
                    message_index,
                    ordinal,
                    call_id=tool_call.id or "",
                    tool_name=tool_call.name,
                    arguments_hash=arguments_hash,
                    recovery_policy=policy.value,
                )
                self._resume_prepared_call_ids.discard(tool_call.id)
            identity_matches = (
                record.get("call_id") == (tool_call.id or "")
                and record.get("tool_name") == tool_call.name
                and record.get("arguments_hash") == arguments_hash
                and record.get("recovery_policy") == policy.value
            )
            if legacy_ambiguous or not identity_matches:
                journal.mark_tool_indeterminate(
                    self.session_id, message_index, ordinal
                )
                reason = (
                    "this consequential tool call predates the execution journal; "
                    "its outcome is unknown, so MimiWork will not retry it automatically"
                    if legacy_ambiguous
                    else "the durable tool record does not match the transcript; automatic retry was blocked"
                )
                return {"action": "indeterminate", "reason": reason, "key": key}

            state = record.get("state")
            if state in {"succeeded", "failed"}:
                try:
                    result = json.loads(record.get("result"))
                except (TypeError, json.JSONDecodeError):
                    journal.mark_tool_indeterminate(
                        self.session_id, message_index, ordinal
                    )
                    return {
                        "action": "indeterminate",
                        "reason": "the committed tool result is unreadable; automatic retry was blocked",
                        "key": key,
                    }
                return {
                    "action": "restore",
                    "result": result,
                    "status": record.get("result_status") or "error",
                    "key": key,
                }
            if state == "running" and policy is RecoveryPolicy.NON_REPLAYABLE:
                journal.mark_tool_indeterminate(
                    self.session_id, message_index, ordinal
                )
                return {
                    "action": "indeterminate",
                    "reason": (
                        "MimiWork stopped while this consequential action was running. "
                        "It may already have completed, so it was not repeated. Verify the "
                        "external result before retrying."
                    ),
                    "key": key,
                }
            if state == "running" and policy is RecoveryPolicy.REPLAY_SAFE:
                journal.reset_replay_safe_tool_run(
                    self.session_id, message_index, ordinal
                )
                return {"action": "proceed", "key": key}
            if state == "indeterminate":
                return {
                    "action": "indeterminate",
                    "reason": (
                        "this action has an indeterminate prior outcome and cannot be "
                        "retried automatically; verify it before trying again"
                    ),
                    "key": key,
                }
            if state not in {"prepared", "running"}:
                return {
                    "action": "indeterminate",
                    "reason": f"unknown durable tool state {state!r}; automatic retry was blocked",
                    "key": key,
                }
            # prepared is known not to have crossed the execution boundary.  A
            # replay-safe read is explicitly reset from running above.
            return {"action": "proceed", "key": key}
        except Exception as exc:
            return {
                "action": "indeterminate",
                "reason": f"could not establish a durable execution record: {exc}",
                "key": key,
            }

    def _cancel_tool_recovery(
        self, tool_call: ToolCall, *, reason: str, status: str
    ) -> None:
        """Make a pre-execution denial/stop terminal in the durable journal."""
        if self.tool_journal is None or not self.session_id:
            return
        position = self._tool_run_position(tool_call)
        if position is None:
            return
        try:
            self.tool_journal.cancel_tool_run(
                self.session_id,
                position[0],
                position[1],
                reason=reason,
                result_status=status,
            )
        except Exception:
            # No side effect occurred, so a persistence failure here is safe.  A
            # future reconstruction will still re-run the permission/stop path.
            pass

    async def _handle_tool_calls(
        self, tool_calls: list[ToolCall]
    ) -> AsyncIterator[Event]:
        """Run one assistant turn's tool calls: authorize all of them first (sequentially —
        approval prompts are interactive), then execute. Low-risk calls (reads, searches)
        run concurrently; everything else runs one at a time in call order."""
        cleared: list[ToolCall] = []
        for tool_call in tool_calls:
            if self._cancel.is_set():
                # Stopped: every remaining call still gets an answer (no orphans).
                yield self._interrupted_tool(tool_call)
                continue
            recovery = (
                None
                if tool_call.name
                in {"request_directory", "propose_plan", "ask_user"}
                else self._prepare_tool_recovery(tool_call)
            )
            yield Event(
                EventType.TOOL_PROPOSED,
                {"name": tool_call.name, "arguments": tool_call.arguments},
            )
            self._audit(tool_call, stage="proposed")
            # `request_directory` and `propose_plan` are interactive: the user decides
            # out-of-band and that decision IS the consent, so they skip the
            # permission/registry path.
            if tool_call.name == "request_directory":
                async for event in self._handle_directory_request(tool_call):
                    yield event
                continue
            if tool_call.name == "propose_plan":
                async for event in self._handle_plan_proposal(tool_call):
                    yield event
                continue
            if tool_call.name == "ask_user":
                async for event in self._handle_ask_user(tool_call):
                    yield event
                continue
            if recovery is not None and recovery["action"] == "restore":
                yield Event(
                    EventType.TOOL_STARTED,
                    {"name": tool_call.name, "recovered": True},
                )
                self._audit(tool_call, stage="recovered", status="restored")
                yield self._record_result(
                    tool_call, recovery["result"], recovery["status"]
                )
                continue
            if recovery is not None and recovery["action"] == "indeterminate":
                reason = recovery["reason"]
                self.messages.append(_tool_error_message(tool_call, reason))
                self._audit(
                    tool_call,
                    stage="finished",
                    status="indeterminate",
                    reason=reason,
                )
                yield Event(
                    EventType.TOOL_FINISHED,
                    {
                        "name": tool_call.name,
                        "status": "indeterminate",
                        "reason": reason,
                        "recovery_required": True,
                    },
                )
                continue
            allowed = False
            async for item in self._authorize(tool_call):
                if isinstance(item, Event):
                    yield item
                else:
                    allowed = item
            if allowed:
                cleared.append(tool_call)

        concurrent = (
            [tc for tc in cleared if self._parallel_safe(tc)]
            if len(cleared) > 1
            else []
        )
        serial = [tc for tc in cleared if tc not in concurrent]

        if concurrent:
            for tool_call in concurrent:
                yield Event(EventType.TOOL_STARTED, {"name": tool_call.name})
                self._audit(tool_call, stage="started")
            outcomes = await asyncio.gather(
                *[asyncio.to_thread(self._execute_sync, tc) for tc in concurrent]
            )
            for tool_call, (result, status) in zip(concurrent, outcomes):
                yield self._record_result(tool_call, result, status)

        for tool_call in serial:
            if self._cancel.is_set():
                yield self._interrupted_tool(tool_call)
                continue
            yield Event(EventType.TOOL_STARTED, {"name": tool_call.name})
            self._audit(tool_call, stage="started")
            result, status = await asyncio.to_thread(self._execute_sync, tool_call)
            yield self._record_result(tool_call, result, status)

    def _interrupted_tool(self, tool_call: ToolCall) -> Event:
        """The stop-path answer for a call that will not run: a tool-error result in the
        history (hosted chat templates reject orphaned tool_calls, and durable-resume
        would otherwise re-prompt it) + the finished event for the tool card."""
        self._cancel_tool_recovery(
            tool_call, reason="interrupted by user", status="interrupted"
        )
        self.messages.append(_tool_error_message(tool_call, "interrupted by user"))
        self._audit(
            tool_call, stage="finished", status="interrupted", reason="user stop"
        )
        return Event(
            EventType.TOOL_FINISHED,
            {"name": tool_call.name, "status": "interrupted", "reason": "stopped"},
        )

    def _parallel_safe(self, tool_call: ToolCall) -> bool:
        # Only metadata-declared low-risk tools (reads, searches, git queries) run
        # concurrently; writes, shell, and anything unannotated stay strictly ordered.
        spec = self.registry.get(tool_call.name)
        metadata = spec.metadata if spec else None
        return getattr(metadata, "risk_level", "") == "low" and not getattr(
            metadata, "requires_approval", False
        )

    async def _authorize(self, tool_call: ToolCall) -> "AsyncIterator[Event | bool]":
        """Permission flow for one call (TOOL_PROPOSED is emitted by the caller). Yields
        its events, then True/False (allowed) last. Denied/unknown calls get their
        tool-error message appended here."""
        from .permissions import standing_rule_candidate

        spec = self.registry.get(tool_call.name)
        metadata = spec.metadata if spec else None

        decision = self.permissions.evaluate(
            tool_call.name, tool_call.arguments, metadata
        )
        allowed = decision.allowed
        reason = decision.reason

        if allowed and decision.rule:
            # A task-scoped standing rule auto-allowed this call: audit the exact rule
            # (§25 invariant — every auto-allowed call cites its rule) and remember it so
            # the tool card can say "allowed by standing rule".
            self._standing_notes[tool_call.id] = decision.rule
            self._audit(
                tool_call, stage="auto_allowed", status="allowed", reason=reason
            )

        if not allowed and decision.needs_user:
            yield Event(
                EventType.PERMISSION_REQUIRED,
                {
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                    "reason": decision.reason,
                    "category": getattr(metadata, "category", ""),
                    # The exact target a standing rule could pin, or None when the call
                    # isn't eligible (no declared target arg / exec risk). Surfaces use it
                    # to offer "Allow every time" on automation-run approval cards only.
                    "standing_target": standing_rule_candidate(
                        tool_call.name,
                        tool_call.arguments,
                        metadata,
                        self.permissions.risk_overrides,
                    ),
                },
            )
            self._audit(tool_call, stage="approval_requested", reason=decision.reason)
            outcome = await self._interruptible(
                self.approver(
                    PermissionRequest(
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                        metadata=metadata,
                        reason=decision.reason,
                        tool_call_id=tool_call.id,
                    )
                ),
                interrupted=ApprovalOutcome.DENY,
            )
            if outcome is ApprovalOutcome.DENY:
                allowed, reason = (
                    False,
                    "interrupted by user" if self._cancel.is_set() else "denied by user",
                )
                self._audit(
                    tool_call,
                    stage="approval_resolved",
                    status="denied",
                    approval=outcome.value,
                    reason=reason,
                )
            else:
                if outcome is ApprovalOutcome.ALWAYS_TOOL:
                    self.permissions.allow_tool_for_session(tool_call.name)
                elif outcome is ApprovalOutcome.ALWAYS_COMMAND:
                    self.permissions.allow_command_for_session(
                        str(tool_call.arguments.get("command", ""))
                    )
                allowed, reason = True, "approved by user"
                self._audit(
                    tool_call,
                    stage="approval_resolved",
                    status="approved",
                    approval=outcome.value,
                    reason=reason,
                )

        if not allowed:
            if spec is None:
                reason = f"unknown tool: {tool_call.name}"
            self._cancel_tool_recovery(tool_call, reason=reason, status="denied")
            self.messages.append(_tool_error_message(tool_call, reason))
            yield Event(
                EventType.TOOL_FINISHED,
                {"name": tool_call.name, "status": "denied", "reason": reason},
            )
            self._audit(tool_call, stage="finished", status="denied", reason=reason)
            yield False
            return

        if spec is None:
            self._cancel_tool_recovery(
                tool_call, reason=f"unknown tool: {tool_call.name}", status="error"
            )
            self.messages.append(
                _tool_error_message(tool_call, f"unknown tool: {tool_call.name}")
            )
            yield Event(
                EventType.TOOL_FINISHED,
                {"name": tool_call.name, "status": "error", "reason": "unknown tool"},
            )
            yield False
            return

        yield True

    def _execute_sync(self, tool_call: ToolCall) -> tuple[Any, str]:
        """Execute one authorized call (runs in a worker thread)."""
        journal_key = self._tool_run_position(tool_call)
        journal = self.tool_journal if self.session_id and journal_key else None
        if journal is not None:
            try:
                journal.start_tool_run(
                    self.session_id, journal_key[0], journal_key[1]
                )
            except Exception as exc:
                return {
                    "error": "tool was not executed because its durable journal could not start",
                    "detail": str(exc),
                    "error_type": "RecoverySafetyError",
                }, "error"

        hooks = getattr(self, "hooks", None)
        result: tuple[Any, str] | None = None
        if self.file_recovery is not None:
            try:
                self.file_recovery.capture(tool_call.name, tool_call.arguments)
            except Exception as exc:
                result = {
                    "error": f"file was not changed because its recovery copy could not be made: {exc}",
                    "error_type": "RecoverySnapshotError",
                }, "error"
        if hooks is not None:
            for hook in hooks.pre:
                if result is not None:
                    break
                try:
                    override = hook(tool_call.name, tool_call.arguments)
                except Exception as exc:
                    result = {"error": f"pre-execute hook failed: {exc}"}, "error"
                    break
                if override is not None:
                    result = override, "ok"
                    break
        if result is None:
            try:
                result = self.registry.execute(tool_call.name, tool_call.arguments), "ok"
            except Exception as exc:
                result = {"error": str(exc), "error_type": type(exc).__name__}, "error"
        if result[1] == "ok" and tool_call.name == "write_file":
            # Text deliverables written through the generic file tool get the same
            # reopen-and-check the Office writers do (those check themselves — they
            # know the absolute target; here we resolve against the workspace root).
            result = (self._verify_written_file(tool_call.arguments, result[0]), "ok")
        if hooks is not None:
            for hook in hooks.post:
                try:
                    hook(tool_call.name, tool_call.arguments, *result)
                except Exception:
                    pass

        if journal is not None:
            try:
                journal.finish_tool_run(
                    self.session_id,
                    journal_key[0],
                    journal_key[1],
                    result=json.dumps(result[0], default=str),
                    result_status=result[1],
                )
            except Exception as exc:
                # The action may already have happened.  Keep its in-memory result so
                # the normal transcript checkpoint can still make progress; the
                # durable row remains `running`, which makes any later restart fail
                # closed instead of repeating it.
                self._audit(
                    tool_call,
                    stage="journal_error",
                    status="indeterminate",
                    reason=str(exc),
                )
        return result

    def _verify_written_file(self, arguments: dict[str, Any], result: Any) -> Any:
        from pathlib import Path as _Path

        from . import deliverable_check

        raw = arguments.get("path") if isinstance(arguments, dict) else None
        if not isinstance(raw, str) or not raw:
            return result
        target = _Path(raw).expanduser()
        if not target.is_absolute():
            root = getattr(self.permissions, "workspace_root", None)
            if root is None:
                return result
            target = _Path(root) / target
        if target.suffix.lower() not in deliverable_check.CHECKED_SUFFIXES:
            return result
        try:
            report = deliverable_check.check(target)
        except Exception:
            return result
        if report["ok"]:
            return result
        shaped: dict[str, Any] = (
            dict(result) if isinstance(result, dict) else {"result": result}
        )
        shaped["verification"] = {
            "ok": False,
            "issues": report["issues"],
            "instruction": "Fix these before telling the user the deliverable is ready.",
        }
        return shaped

    def _record_result(self, tool_call: ToolCall, result: Any, status: str) -> Event:
        # A `_display` key on a tool result is user-facing metadata the AGENT must
        # never see (e.g. how many gmail hits the privacy filters hid — a count
        # the model could probe around). Lift it onto the message as a sidecar
        # (like `source`), stripped from every provider feed in
        # `_outbound_messages` but persisted for the GUI's tool card.
        display: Optional[dict[str, Any]] = None
        if isinstance(result, dict) and "_display" in result:
            display = result.get("_display") or None
            result = {k: v for k, v in result.items() if k != "_display"}
        message = _tool_result_message(tool_call, result, self.spill)
        if display:
            message["_display"] = display
        self.messages.append(message)
        hidden = int((display or {}).get("hidden_by_filters") or 0)
        stripped = int((display or {}).get("hidden_fields") or 0)
        if hidden or stripped:
            # The out-of-band trace the user CAN see: rule class + count, never content.
            parts = []
            if hidden:
                parts.append(f"{hidden} result(s) hidden")
            if stripped:
                parts.append(f"{stripped} field value(s) stripped")
            self._audit(
                tool_call,
                stage="filtered",
                status="hidden",
                reason=" · ".join(parts) + " by privacy filters",
            )
        self._audit(
            tool_call,
            stage="finished",
            status=status,
            result=result,
            result_preview=_preview(result),
        )
        rule = self._standing_notes.pop(tool_call.id, "")
        return Event(
            EventType.TOOL_FINISHED,
            {
                "name": tool_call.name,
                "status": status,
                "result_preview": _preview(result),
                **({"display": display} if display else {}),
                **({"standing_rule": rule} if rule else {}),
            },
        )

    def _begin_turn(self) -> None:
        self._turn_started = time.monotonic()
        self._turn_approvals = 0
        self._turn_tools = set()
        self._turn_planned = False
        if self.file_recovery is not None:
            self.file_recovery.begin_turn()

    def _close_turn(self) -> dict[str, Any]:
        """Charge the user's side of this turn and hand back the running totals.

        The waiting time is real elapsed time, not a guess — the one number in the
        whole estimate that is measured rather than modelled."""
        elapsed = time.monotonic() - self._turn_started if self._turn_started else 0.0
        self.time_saved.add_turn(elapsed, approvals=self._turn_approvals)
        rung = classify_turn(
            tools=self._turn_tools,
            scheduled=self.turn_scheduled,
            planned=self._turn_planned,
        )
        self.five_a[rung] = self.five_a.get(rung, 0) + 1
        self._turn_started = 0.0
        self._turn_approvals = 0
        totals = self.time_saved.as_dict()
        totals["five_a"] = dict(self.five_a)
        return totals

    def _audit(self, tool_call: ToolCall, **event: Any) -> None:
        # Every finished tool call is also an entry in the time estimate; approvals are
        # counted because reading a card and deciding is time the user spent.
        stage = event.get("stage")
        if stage == "finished" and event.get("status") == "ok":
            self.time_saved.add_call(
                tool_call.name, tool_call.arguments, event.get("result")
            )
            self._turn_tools.add(tool_call.name)
            if tool_call.name == "propose_plan":
                self._turn_planned = True
        elif stage == "approval_requested":
            self._turn_approvals += 1
        if self.audit_sink is None:
            return
        payload = {
            **self.audit_context,
            "tool": tool_call.name,
            "arguments": tool_call.arguments,
            **event,
        }
        try:
            self.audit_sink(payload)
        except Exception:
            pass

    async def _handle_plan_proposal(self, tool_call: ToolCall) -> AsyncIterator[Event]:
        """Emit the plan for review, await the user's out-of-band decision, and apply it:
        approval flips the live PermissionEngine out of plan mode (the same session keeps
        going, with all its exploration context); rejection keeps plan mode and returns
        the user's feedback so the agent can revise."""
        args = tool_call.arguments or {}
        plan = str(args.get("plan", ""))
        if self.permissions.mode is not Mode.PLAN:
            # The tool is always registered (mode can flip mid-session), but proposing a
            # plan only means something while the session is actually in plan mode. The
            # right next step differs by mode: discuss stays read-only, so the agent
            # should talk through the change; write-capable modes should just do it.
            if self.permissions.mode is Mode.DISCUSS:
                error = (
                    "not in plan mode — this is discuss mode (read-only), so describe "
                    "the proposed changes in chat instead"
                )
            else:
                error = "not in plan mode — proceed with the work directly"
            result: dict[str, Any] = {"approved": False, "error": error}
        elif self.plan_approver is None:
            result = {
                "approved": False,
                "error": "plan approval isn't available here",
            }
        else:
            yield Event(EventType.PLAN_PROPOSED, {"plan": plan})
            self._audit(tool_call, stage="plan_proposed")
            result = await self._interruptible(
                self.plan_approver(dict(args), tool_call.id),
                interrupted={"approved": False, "error": "interrupted by user"},
            ) or {
                "approved": False,
                "error": "no response",
            }

        if result.get("approved"):
            # The approver may pick the post-plan mode ("interactive" asks per write,
            # "auto" executes the approved plan without further prompts).
            try:
                self.permissions.mode = Mode(str(result.get("mode", "interactive")))
            except ValueError:
                self.permissions.mode = Mode.INTERACTIVE
            result = {
                **result,
                "mode": self.permissions.mode.value,
                "note": "plan approved — implement it now",
            }

        status = "ok" if result.get("approved") else "denied"
        self.messages.append(_tool_result_message(tool_call, result))
        self._audit(
            tool_call,
            stage="finished",
            status=status,
            result=result,
            result_preview=_preview(result),
        )
        yield Event(
            EventType.TOOL_FINISHED,
            {
                "name": tool_call.name,
                "status": status,
                "result_preview": _preview(result),
            },
        )

    async def _handle_directory_request(
        self, tool_call: ToolCall
    ) -> AsyncIterator[Event]:
        """Emit the grant prompt, await the user's out-of-band decision (which the requester also
        applies to this session's roots), and return the outcome as the tool result."""
        args = tool_call.arguments or {}
        if self.directory_requester is None:
            result: dict[str, Any] = {
                "granted": False,
                "error": "directory requests aren't available here",
            }
        else:
            yield Event(
                EventType.DIRECTORY_REQUESTED,
                {
                    "reason": str(args.get("reason", "")),
                    "path": str(args.get("path", "")),
                    "writable": bool(args.get("writable", False)),
                },
            )
            self._audit(
                tool_call,
                stage="directory_requested",
                reason=str(args.get("reason", "")),
            )
            result = await self._interruptible(
                self.directory_requester(dict(args), tool_call.id),
                interrupted={"granted": False, "error": "interrupted by user"},
            ) or {
                "granted": False,
                "error": "no response",
            }

        status = "ok" if result.get("granted") else "denied"
        self.messages.append(_tool_result_message(tool_call, result))
        self._audit(
            tool_call,
            stage="finished",
            status=status,
            result=result,
            result_preview=_preview(result),
        )
        yield Event(
            EventType.TOOL_FINISHED,
            {
                "name": tool_call.name,
                "status": status,
                "result_preview": _preview(result),
            },
        )

    async def _handle_ask_user(self, tool_call: ToolCall) -> AsyncIterator[Event]:
        """Emit the question, await the user's out-of-band answer (inline in the live session or
        from the Inbox when unattended), and return it as the tool result."""
        args = tool_call.arguments or {}
        question = str(args.get("question", "")).strip()
        # Grouped form (OPE-51): `questions` alone is a valid call — the singular field may be
        # empty. The asker normalizes/validates the entries; here only "is anything asked?".
        if not question:
            for entry in args.get("questions") or []:
                if isinstance(entry, dict) and str(entry.get("question", "")).strip():
                    question = str(entry["question"]).strip()
                    break
        if self.question_asker is None or not question:
            result: dict[str, Any] = {
                "answer": "",
                "error": (
                    "no question was asked"
                    if not question
                    else "asking isn't available here"
                ),
            }
        else:
            # The asker is mode-aware (attended → live inline prompt; unattended → Inbox), so it
            # owns surfacing the question. The engine just awaits the answer.
            self._audit(tool_call, stage="question_requested", reason=question)
            result = await self._interruptible(
                self.question_asker(dict(args), tool_call.id),
                interrupted={"answer": "", "error": "interrupted by user"},
            ) or {
                "answer": "",
                "error": "no response",
            }

        status = "ok" if (result.get("answer") or result.get("answers")) else "denied"
        self.messages.append(_tool_result_message(tool_call, result))
        self._audit(
            tool_call,
            stage="finished",
            status=status,
            result=result,
            result_preview=_preview(result),
        )
        yield Event(
            EventType.TOOL_FINISHED,
            {
                "name": tool_call.name,
                "status": status,
                "result_preview": _preview(result),
            },
        )

    def drain_pending_steering(self) -> list[str]:
        """Take (and clear) queued steering that no live loop consumed — the race where
        the user's mid-run instruction arrived just as the turn finished. Only unsourced
        (locally typed) entries are taken; connector-sourced steers stay with their own
        delivery plumbing."""
        taken = [text for text, source in self._steering if source is None]
        if taken:
            self._steering = [(t, s) for t, s in self._steering if s is not None]
        return taken

    def _inject_steering(self) -> None:
        for text, source in self._steering:
            message: dict[str, Any] = {
                "role": "user",
                "content": text,
                "ts": time.time(),
            }
            if source is not None:
                message["source"] = source
            self.messages.append(message)
        self._steering = []

    def _outbound_messages(self) -> list[dict[str, Any]]:
        """`self.messages` prepared for the provider. The SOLE provider feed (see `_astream`).

        Every message is stripped of the display-only sidecars — `source`, `_display`, and
        `ts` — (providers reject unknown keys), unconditionally — whether or not a
        `<system-context>` block is added. When a context
        provider yields a non-empty string, an ephemeral `<system-context>` block is appended to the
        last user message. Never mutates `self.messages`, so neither the strip nor the block is
        persisted/replayed.
        """
        # Strip the display-only sidecars — `source` (connector cards), `_display`
        # (e.g. filter-hidden counts), `ts` (append-time timestamps), `reasoning`
        # (thinking text), and `usage` (token counts) — copying only messages that carry
        # one. Whole `notice` messages (error/interrupted/model-switch markers) are
        # display-only too: dropped entirely.
        _SIDECARS = ("source", "_display", "ts", "reasoning", "usage", "steering")
        # Auto-compaction (OPE-27): everything before the boundary is represented by the
        # compacted block. Outbound-only — the canonical history stays intact — and the
        # block+tail are byte-stable between turns, so prompt caching keeps working.
        source_messages = _compaction.apply_to_outbound(
            self.messages, self.compaction_state
        )
        out = [
            (
                {k: v for k, v in msg.items() if k not in _SIDECARS}
                if any(s in msg for s in _SIDECARS)
                else msg
            )
            for msg in source_messages
            if msg.get("role") != "notice"
        ]
        # PDF attachments (stored as `file` parts) are adapted to the ACTIVE model right
        # here — never in the persisted history — so a mid-session model switch always
        # re-decides: native PDF models get the real document, the rest get the local
        # text-extract/page-image fallback (pdf_support.py).
        if any(
            isinstance(p, dict) and p.get("type") == "file"
            for msg in out
            if isinstance(msg.get("content"), list)
            for p in msg["content"]
        ):
            caps = self.provider.capabilities(self.model)
            if not getattr(caps, "pdf", False):
                from . import pdf_support

                out = [
                    (
                        {
                            **msg,
                            "content": pdf_support.adapt_content(msg["content"], caps),
                        }
                        if isinstance(msg.get("content"), list)
                        else msg
                    )
                    for msg in out
                ]

        # Images get the same per-turn treatment: a model without vision receives a visible
        # placeholder instead of a payload it would reject. Like the PDF path, this re-decides
        # per call, so a mid-session switch to/from a vision model always does the right thing.
        if any(
            isinstance(p, dict) and p.get("type") == "image_url"
            for msg in out
            if isinstance(msg.get("content"), list)
            for p in msg["content"]
        ):
            caps = self.provider.capabilities(self.model)
            if not getattr(caps, "vision", False):
                placeholder = {
                    "type": "text",
                    "text": "[image attachment — not viewable by this model]",
                }
                out = [
                    (
                        {
                            **msg,
                            "content": [
                                (
                                    placeholder
                                    if isinstance(p, dict)
                                    and p.get("type") == "image_url"
                                    else p
                                )
                                for p in msg["content"]
                            ],
                        }
                        if isinstance(msg.get("content"), list)
                        else msg
                    )
                    for msg in out
                ]

        context = (
            self.context_provider() if self.context_provider is not None else ""
        ) or ""
        if not context:
            return out
        block = f"\n\n<system-context>\n{context}\n</system-context>"
        for i in range(len(out) - 1, -1, -1):
            if out[i].get("role") != "user":
                continue
            msg = dict(out[i])
            content = msg.get("content")
            if isinstance(content, str):
                msg["content"] = content + block
            elif isinstance(content, list):  # content-parts (text + images)
                msg["content"] = [*content, {"type": "text", "text": block}]
            else:
                msg["content"] = block
            out[i] = msg
            break
        return out


def _assistant_message(turn: AssistantTurn, model: Optional[str] = None) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": turn.text or "",
        "ts": time.time(),
    }
    if turn.usage is not None:
        # Display/aggregation sidecar (like `reasoning`): persisted with the message,
        # stripped before provider calls. Tagged with the model that produced it so
        # per-model rollups survive mid-session model switches.
        message["usage"] = {"model": model, **turn.usage.as_dict()}
    if turn.reasoning:
        # Display-only thinking text — rendered by the GUI, stripped for every provider
        # (`_outbound_messages`); provider-private replay blocks go via `extras` instead.
        message["reasoning"] = turn.reasoning
    if turn.extras:
        # Provider-private sidecars (e.g. `_gemini` thought signatures) persist with the
        # message; the owning provider reattaches them, the rest strip them (base.py).
        message.update(turn.extras)
    if turn.tool_calls:
        message["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in turn.tool_calls
        ]
    return message


def _tool_result_message(
    tool_call: ToolCall, result: Any, spill: Any = None
) -> dict[str, Any]:
    content = result if isinstance(result, str) else json.dumps(result, default=str)
    # The one seam where a tool result becomes model-visible content, so it is where an
    # oversized result is redirected to a file instead of eating the context window.
    if spill is not None:
        content = spill.maybe_spill(content, label=tool_call.name)
    return {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": content,
        "ts": time.time(),
    }


def _tool_error_message(tool_call: ToolCall, reason: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps({"error": "tool call not executed", "reason": reason}),
        "ts": time.time(),
    }


def _preview(value: Any, max_chars: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = text.replace("\n", "\\n")
    return text if len(text) <= max_chars else text[: max_chars - 3] + "..."
