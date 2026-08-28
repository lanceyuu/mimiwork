# FrontierAgent adoptions (built 2026-08-28)

Owner ask: "can you copy anything and use any feature or inspiration from
github.com/ApodexAI/FrontierAgent?" License checked first: Apache-2.0 —
compatible with this repo's MIT, attribution kept (README Acknowledgements +
module headers).

FrontierAgent is a 152k-line agent framework; MimiWork already has an engine,
permissions, sub-agents and automations, so wholesale copying would be noise.
Two mechanisms were worth taking, both because they map to money or trust here.

## 1. Steer while running (their "asynchronous intervention")

Theirs: type while an agent runs; the instruction is queued and injected at the
next safe turn boundary without discarding the run.

Ours before: the composer blocked sending mid-turn AND the websocket rejected
mid-turn messages outright ("This session is already running a turn."). The
engine ALREADY had `queue_steering()` — built for Slack follow-up tags — the
desktop path just never used it.

Now: a plain typed message while Mimi runs → `steer_queued` ack → injected by
the loop between tool iterations (`_inject_steering`, which existed). A steer
that lands in the turn's closing instants is drained in run_turn's finally and
runs as its own follow-up turn — never lost, never silently deferred into some
future turn (`drain_pending_steering`, unsourced entries only: connector steers
stay with connector plumbing). Attachments and /skill runs still wait — they
need a fresh turn's framing. Composer: Enter sends while running; placeholder
says it steers; Stop unchanged.

## 2. Repetition guard (`coworker/repetition.py`)

Theirs: word-bigram Jaccard over normalised recent turns; hint on a streak,
optional stop. Adapted rather than vendored: per-turn scope inside the tool
loop (their cross-turn observer shape doesn't exist here), signature =
assistant text + tool names + sorted args, min_chars low because the signature
is structured, hint at 3, stop at 6 with its own TURN_END status
(`repetition_stop`) — checked BEFORE the tools run so the identical lap is
skipped, not executed once more. Stop is ON here (their default is off):
every lap costs the user QualiTaTi credits, so a looping model is a billing
bug, not a curiosity. The guard proved itself immediately: it fires on
tests/test_subagent.py's endless-explorer fixture before the max_iterations
rail that test was written for.

## Looked at, deliberately not taken

- **Agent Team / task board** — MimiWork's explore sub-agent + todo panel cover
  the need at this product's scale; a coordinator layer is complexity without a
  current user.
- **/revert (session-wide file restore)** — valuable but heavy; MimiWork's
  approval-gated writes + artifacts panel hold the line for now.
- **/inputs · /workspace · /outputs sandbox split** — MimiWork's granted-roots
  model (per-folder read/write grants) is the same guarantee with a UX users
  already know.
