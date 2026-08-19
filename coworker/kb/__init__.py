"""Mimi's offline knowledge base — 4,000 curated research-methods entries.

The content ships with the app (``knowledge_base.jsonl``, same corpus the
QualiTaTi products carry): 2,000 qualitative-methodology Q&As and 2,000
exemplar interview questions across consumer/UX/health/education/work domains.
``search()`` is Okapi BM25 over title+content with a postings-list index built
lazily on first use — offline, no embeddings, no network.
"""

from __future__ import annotations

import json
import math
import re
import threading
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Optional

# Same tokenizer contract as the QualiTaTi apps: lowercase, split on anything
# that isn't latin alnum or CJK, drop single-char tokens. Parity matters more
# than linguistic sophistication — the corpus was authored against it.
_TOKEN_SPLIT = re.compile(r"[^a-z0-9一-鿿]+")

_K1 = 1.4
_B = 0.75

COLLECTIONS = ("methodology_qa", "interview_questions")


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_SPLIT.split(text.lower()) if len(t) > 1]


@dataclass
class _Index:
    docs: list[dict[str, Any]] = field(default_factory=list)
    doc_len: list[int] = field(default_factory=list)
    avg_len: float = 0.0
    # term -> {doc_index: term_frequency}. A postings list makes each query
    # O(matching docs), not O(corpus) like the original linear-scan port.
    postings: dict[str, dict[int, int]] = field(default_factory=dict)


_index: Optional[_Index] = None
_index_lock = threading.Lock()


def _build_index() -> _Index:
    idx = _Index()
    data = resources.files(__package__).joinpath("knowledge_base.jsonl")
    with data.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except ValueError:
                continue  # a corrupt line is a data bug, not a search outage
            i = len(idx.docs)
            idx.docs.append(doc)
            tokens = _tokenize(f"{doc.get('title') or ''} {doc.get('content') or ''}")
            idx.doc_len.append(len(tokens))
            for tok in tokens:
                idx.postings.setdefault(tok, {})
                idx.postings[tok][i] = idx.postings[tok].get(i, 0) + 1
    idx.avg_len = (sum(idx.doc_len) / len(idx.doc_len)) if idx.doc_len else 0.0
    return idx


def _get_index() -> _Index:
    global _index
    if _index is None:
        with _index_lock:
            if _index is None:
                _index = _build_index()
    return _index


def search(
    query: str, *, k: int = 5, collection: Optional[str] = None
) -> list[dict[str, Any]]:
    """Top-``k`` entries by BM25; optional collection filter. Each result is the
    raw KB record plus a ``score``."""
    idx = _get_index()
    n_docs = len(idx.docs)
    if not n_docs:
        return []
    scores: dict[int, float] = {}
    for tok in set(_tokenize(query)):
        posting = idx.postings.get(tok)
        if not posting:
            continue
        df = len(posting)
        id_f = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
        for doc_i, tf in posting.items():
            denom = tf + _K1 * (1 - _B + _B * idx.doc_len[doc_i] / (idx.avg_len or 1))
            scores[doc_i] = scores.get(doc_i, 0.0) + id_f * (tf * (_K1 + 1)) / denom
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    out: list[dict[str, Any]] = []
    for doc_i, score in ranked:
        doc = idx.docs[doc_i]
        if collection and doc.get("collection") != collection:
            continue
        out.append({**doc, "score": round(score, 4)})
        if len(out) >= k:
            break
    return out
