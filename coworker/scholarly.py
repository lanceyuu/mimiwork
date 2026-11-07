"""Every network call for paper search and reference checks (spec 2026-11-07).

One module so both features share the rules that keep MimiWork a good citizen of free
services and keep a researcher's key out of logs: the polite-pool contact on every
Crossref call, one pacing limiter, no cache (a retraction must never hide behind an old
reply), and the OpenAlex key read at every call so a key saved mid-session works at once.
"""

from __future__ import annotations

import html
import logging
import re
import threading
import time
from typing import Any, Optional
from urllib.parse import quote

import httpx

from .secrets import SecretStore

CONTACT = "contact@qualitati.com"  # the project's public address, never the researcher's
USER_AGENT = f"MimiWork (https://qualitati.com; mailto:{CONTACT})"
CROSSREF = "https://api.crossref.org"
OPENALEX = "https://api.openalex.org"
DOI_ORG = "https://doi.org"
TIMEOUT = 10.0
OPENALEX_PROFILE = "openalex:default"

# httpx logs every request URL at INFO, and an OpenAlex URL carries the researcher's key.
logging.getLogger("httpx").setLevel(logging.WARNING)

_transport: Optional[httpx.BaseTransport] = None
_sleep = time.sleep
_clock = time.monotonic


def set_transport(transport: Optional[httpx.BaseTransport]) -> None:
    """Tests serve recorded replies through an httpx.MockTransport."""
    global _transport
    _transport = transport


class _Pace:
    """At most `limit` requests in flight, and one started every `interval` seconds:
    Crossref's polite pool allows three of each, its public pool one."""

    def __init__(self, limit: int = 3, interval: float = 1 / 3) -> None:
        self.limit, self.interval = limit, interval
        self._busy = 0
        self._next = 0.0
        self._cond = threading.Condition()

    def slow_down(self) -> None:
        # ponytail: once slowed, slowed until the sidecar restarts; a per-run reset can
        # come if the public pool turns out to be a passing state.
        with self._cond:
            self.limit, self.interval = 1, 1.0

    def __enter__(self) -> "_Pace":
        with self._cond:
            while self._busy >= self.limit:
                self._cond.wait()
            self._busy += 1
            now = _clock()
            start = max(now, self._next)
            self._next = start + self.interval
        if start > now:
            _sleep(start - now)
        return self

    def __exit__(self, *exc: Any) -> None:
        with self._cond:
            self._busy -= 1
            self._cond.notify_all()


pace = _Pace()


def _retry_after(response: httpx.Response) -> float:
    try:
        return max(0.0, min(float(response.headers.get("retry-after", "1")), 10.0))
    except ValueError:
        return 1.0


def _get(
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    paced: bool = True,
    retry_429: bool = True,
) -> Optional[httpx.Response]:
    """One GET, retried once on 5xx (and on 429 unless told not to); None when the network
    itself failed. Redirects are never followed here: a DOI's registrant chooses where it
    resolves, so only _negotiate may follow one, hop by hop, onto the registries."""
    sent = {"User-Agent": USER_AGENT, **(headers or {})}
    response: Optional[httpx.Response] = None
    for attempt in (0, 1):
        try:
            with httpx.Client(transport=_transport, timeout=TIMEOUT, follow_redirects=False) as client:
                if paced:
                    with pace:
                        response = client.get(url, params=params, headers=sent)
                else:
                    response = client.get(url, params=params, headers=sent)
        except httpx.HTTPError:
            return None
        pool = response.headers.get("x-api-pool")
        if pool is not None and not pool.startswith("polite"):
            pace.slow_down()
        busy = (response.status_code == 429 and retry_429) or response.status_code >= 500
        if busy and attempt == 0:
            _sleep(_retry_after(response))
            continue
        return response
    return response


def _failed(code: str = "lookup_failed", **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": code, **extra}


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)


def normalise_doi(raw: Any) -> Optional[str]:
    """A DOI as people print it, reduced to its comparable form; None when it is not one."""
    if not isinstance(raw, str):
        return None
    doi = re.sub(r"\s+", "", _DOI_PREFIX.sub("", raw.strip()))
    while doi:
        if doi[-1] in ".,;":
            doi = doi[:-1]
        elif doi[-1] == ")" and doi.count("(") < doi.count(")"):
            doi = doi[:-1]
        elif doi[-1] == "]" and doi.count("[") < doi.count("]"):
            doi = doi[:-1]
        else:
            break
    doi = doi.lower()
    # A "." or ".." segment would be collapsed by the URL layer into another path on
    # doi.org (its resolver instead of its /ra/ API), so it is never a DOI here.
    if any(seg in (".", "..") for seg in doi.split("/")):
        return None
    return doi if _DOI.match(doi) else None


def clean(text: Any) -> str:
    """Tags stripped and entities decoded: Crossref titles carry <i>, <sub> and &amp;."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", str(text or ""))).split())


# Crossref renames a retracted paper "RETRACTED: …"; the paper a researcher cites has no
# such prefix, and keeping it would fail the title test or flag the title as different.
_RETRACTED = re.compile(r"^(?:retracted|withdrawn)(?:\s+article)?\s*[:.\-–—]\s*", re.I)


def record_title(record: dict[str, Any]) -> tuple[str, str, bool]:
    """(full title, main title, has a subtitle) of a Crossref work."""
    title = _RETRACTED.sub("", clean((record.get("title") or [""])[0]))
    subtitle = clean((record.get("subtitle") or [""])[0])
    if subtitle and subtitle.lower() not in title.lower():
        return f"{title}: {subtitle}", title, True
    main, colon, _ = title.partition(":")
    return title, (main.strip() if colon else title), bool(colon)


_STRENGTH = {"none": 0, "concern": 1, "partly_retracted": 2, "retracted": 3}
_NOTICE = {
    "retraction": "retracted",
    "withdrawal": "retracted",
    "removal": "retracted",
    "partial_retraction": "partly_retracted",
    "expression_of_concern": "concern",
}


def retraction(record: dict[str, Any]) -> dict[str, Any]:
    """The strongest Retraction Watch notice on a Crossref work; corrections are not one."""
    out: dict[str, Any] = {"status": "none", "year": None, "notice": None}
    for update in record.get("updated-by") or []:
        kind = str(update.get("type") or "").lower().replace("-", "_")
        status = _NOTICE.get(kind)
        if status is None or _STRENGTH[status] <= _STRENGTH[out["status"]]:
            continue
        parts = ((update.get("updated") or {}).get("date-parts") or [[None]])[0] or [None]
        out = {"status": status, "year": parts[0], "notice": update.get("DOI")}
    return out


def _path(doi: str) -> str:
    return quote(doi, safe="/")


def crossref_work(doi: str) -> dict[str, Any]:
    response = _get(f"{CROSSREF}/works/{_path(doi)}", params={"mailto": CONTACT})
    if response is None:
        return _failed()
    if response.status_code == 200:
        data = _json(response)
        if isinstance(data, dict) and isinstance(data.get("message"), dict):
            return {"ok": True, "record": data["message"]}
        return _failed()
    if response.status_code == 404:
        return _agency(doi)
    return _failed()


def _agency(doi: str) -> dict[str, Any]:
    """Who registered a DOI Crossref does not know: arXiv's DOIs are DataCite's, for one."""
    response = _get(f"{DOI_ORG}/ra/{_path(doi)}")
    rows = _json(response) if response is not None and response.status_code == 200 else None
    row = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
    agency = str(row.get("RA") or "")
    if agency and agency.lower() != "crossref":
        return _failed("outside_crossref", agency=agency)
    if "does not exist" in str(row.get("status") or "").lower():
        return _failed("no_such_doi")
    return _failed()  # Crossref says 404 but the registry says Crossref: a passing fault


def crossref_search(
    text: str, rows: int = 5, *, field: str = "query.bibliographic", filters: str = ""
) -> dict[str, Any]:
    params: dict[str, Any] = {field: text[:500], "rows": rows, "mailto": CONTACT}
    if filters:
        params["filter"] = filters
    response = _get(f"{CROSSREF}/works", params=params)
    data = _json(response) if response is not None and response.status_code == 200 else None
    items = (data or {}).get("message", {}).get("items") if isinstance(data, dict) else None
    return {"ok": True, "items": items} if isinstance(items, list) else _failed()


# Where doi.org sends a content-negotiation request (probed 2026-11-07). Any other hop is
# the registrant's landing page, or worse a local or private address: never followed.
_REGISTRIES = ("doi.org", "crossref.org", "crosscite.org", "datacite.org")


def _registry(url: httpx.URL) -> bool:
    host = url.host or ""
    if url.scheme != "https" or url.port is not None or url.userinfo:
        return False
    return any(host == h or host.endswith("." + h) for h in _REGISTRIES)


def _negotiate(doi: str, accept: str) -> Optional[httpx.Response]:
    url = httpx.URL(f"{DOI_ORG}/{_path(doi)}")
    for _ in range(5):
        response = _get(str(url), headers={"Accept": accept})
        if response is None or not response.is_redirect:
            return response
        url = url.join(response.headers.get("location", ""))
        if not _registry(url):
            break
    return httpx.Response(406)  # read by every caller as "doi.org could not give it"


def csl_record(doi: str) -> dict[str, Any]:
    response = _negotiate(doi, "application/vnd.citationstyles.csl+json")
    if response is None:
        return _failed()
    if response.status_code == 404:
        return _failed("no_such_doi")
    kind = response.headers.get("content-type", "")
    json_reply = response.status_code == 200 and kind.split(";")[0].strip() in (
        "application/vnd.citationstyles.csl+json",
        "application/json",
    )
    data = _json(response) if json_reply else None
    return {"ok": True, "record": data} if isinstance(data, dict) else _failed()


def _text_reply(doi: str, accept: str, expect: str) -> dict[str, Any]:
    response = _negotiate(doi, accept)
    if response is None:
        return _failed()
    if response.status_code == 404:
        return _failed("no_such_doi")
    # Only the type asked for: a DOI that resolves straight to a PDF or a landing page must
    # never reach the model as "the reference".
    kind = response.headers.get("content-type", "")
    if response.status_code != 200 or not kind.startswith(expect):
        return _failed("cannot_format")
    return {"ok": True, "text": response.text}


def formatted(doi: str, style: str) -> dict[str, Any]:
    out = _text_reply(doi, f"text/x-bibliography; style={style}", "text/x-bibliography")
    return {"ok": True, "text": clean(out["text"])} if out["ok"] else out


def bibtex(doi: str) -> dict[str, Any]:
    out = _text_reply(doi, "application/x-bibtex", "application/x-bibtex")
    return {"ok": True, "text": out["text"].strip()} if out["ok"] else out


def _openalex(params: dict[str, Any], secrets: Optional[SecretStore]) -> dict[str, Any]:
    profile = (secrets or SecretStore()).get(OPENALEX_PROFILE) or {}
    key = profile.get("api_key") if isinstance(profile, dict) else None
    if key:
        params = {**params, "api_key": key}
    # Not paced (OpenAlex meters by budget, not by rate) and never retried on 429: the
    # budget resets daily, so waiting would only stall the check.
    response = _get(f"{OPENALEX}/works", params=params, paced=False, retry_429=False)
    if response is None:
        return _failed()
    if response.status_code in (401, 403) and key:
        return _failed("openalex_key_refused")
    if response.status_code in (402, 429):
        return _failed("openalex_limit")
    data = _json(response) if response.status_code == 200 else None
    results = data.get("results") if isinstance(data, dict) else None
    return {"ok": True, "results": results} if isinstance(results, list) else _failed()


def openalex_search(
    query: str,
    from_year: Optional[int] = None,
    to_year: Optional[int] = None,
    n: int = 5,
    *,
    secrets: Optional[SecretStore] = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"search": query, "per-page": max(1, min(int(n or 5), 10))}
    years = []
    if isinstance(from_year, int):
        years.append(f"from_publication_date:{from_year}-01-01")
    if isinstance(to_year, int):
        years.append(f"to_publication_date:{to_year}-12-31")
    if years:
        params["filter"] = ",".join(years)
    return _openalex(params, secrets)


def openalex_title(title: str, *, secrets: Optional[SecretStore] = None) -> dict[str, Any]:
    return _openalex({"search": title[:300], "per-page": 5}, secrets)
