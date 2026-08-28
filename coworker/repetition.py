"""Catch a model repeating itself before it burns the user's credits.

A stuck model re-sends near-identical turns — same prose, same tool call — and every
lap costs real money (QualiTaTi credits) while producing nothing. Within one
turn's tool loop this guard watches the assistant's output; after a few near-identical
iterations it injects a corrective nudge, and if the model still doesn't change course
it stops the turn with a named status instead of riding to max_iterations.

Similarity is word-bigram Jaccard over normalised text: robust to small wording edits
("in this exact format" → "in the format below") that would fool exact matching, cheap
enough to run every iteration, and language-agnostic enough for CJK (whitespace-less
text degrades to punctuation chunks, which still differ between genuinely new turns).

The detection approach (shingle similarity over a sliding window, hint-then-stop
escalation) is adapted from FrontierAgent by Apodex AI
(https://github.com/ApodexAI/FrontierAgent, Apache License 2.0).
"""

from __future__ import annotations

import re
from collections import deque

_WHITESPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[!-/:-@\[-`{-~]+")

#: What the model is told when it starts looping. Deliberately concrete: name the
#: symptom and the ways out, because "please stop repeating" reliably gets repeated.
HINT = (
    "Your last few responses are near-duplicates of each other — the same text and "
    "the same tool call, with no new result. Repeating it again will not change the "
    "outcome. Change course now: use a different tool or different arguments, act on "
    "the information you already have, or if the task cannot proceed, say so plainly "
    "and finish the turn."
)


def _shingles(text: str, n: int = 2) -> set[str]:
    cleaned = _PUNCT.sub(" ", _WHITESPACE.sub(" ", text.strip().lower()))
    tokens = cleaned.split()
    if not tokens:
        return set()
    if len(tokens) < n:
        return set(tokens)
    return {" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


class RepetitionGuard:
    """Per-turn tracker. Feed each continuing assistant iteration; read the verdict.

    ``observe`` returns None (fine), "hint" (exactly once, when the streak reaches
    ``hint_after``) or "stop" (streak reached ``stop_after``). A short signature —
    under ``min_chars`` after normalisation — is ignored rather than matched: brief
    acknowledgements legitimately repeat.
    """

    def __init__(
        self,
        *,
        window: int = 4,
        threshold: float = 0.8,
        min_chars: int = 40,
        hint_after: int = 3,
        stop_after: int = 6,
    ) -> None:
        if hint_after < 2 or stop_after < hint_after:
            raise ValueError("need hint_after ≥ 2 and stop_after ≥ hint_after")
        self.threshold = threshold
        self.min_chars = min_chars
        self.hint_after = hint_after
        self.stop_after = stop_after
        self._history: deque[set[str]] = deque(maxlen=window)
        self._streak = 0
        self._hinted = False

    def observe(self, signature: str) -> str | None:
        text = _WHITESPACE.sub(" ", signature.strip().lower())
        if len(text) < self.min_chars:
            return None
        current = _shingles(text)
        matched = any(
            _jaccard(current, prior) >= self.threshold for prior in self._history
        )
        self._history.append(current)
        if not matched:
            # The current turn seeds a potential new run: the next match makes 2.
            self._streak = 1
            self._hinted = False
            return None
        self._streak += 1
        if self._streak >= self.stop_after:
            return "stop"
        if self._streak >= self.hint_after and not self._hinted:
            self._hinted = True
            return "hint"
        return None
