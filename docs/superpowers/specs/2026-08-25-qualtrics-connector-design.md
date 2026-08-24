# Qualtrics connector (built 2026-08-25)

Owner ask: "is it possible for you to build a plugin or connector to Qualtrics?" —
https://api.qualtrics.com/. Yes: token auth, plain REST, no OAuth broker, so it fits the
existing `api_token` connector shape exactly.

## Why this connector, in this app

MimiWork's centre of gravity is survey and interview work — the Data Analyst reads SPSS
variable and value labels, QualiTaTi's own surveys are already reachable. Qualtrics is
where a large share of that data actually lives, and the manual path today is: log in,
export, unzip, find the file, remember what `Q4_1` meant. This collapses that into
"analyse my December wave".

## The line: metadata is free, answers ask

* `qualtrics_list_surveys`, `qualtrics_get_survey`, `qualtrics_list_distributions` are
  **reads** — survey names, question wording, send/finish counts. Nothing a respondent
  wrote. Connector reads never gate (§36), and these deserve that.
* `qualtrics_export_responses` is registered as a **write** in `tool_defs.py`, so the
  permission engine asks before it runs. It pulls other people's answers off a server and
  writes them onto this disk; that is the user's call each time. Same line the owner drew
  for QualiTaTi research data on 2026-08-23.

Nothing in the surface creates, edits, activates or deletes anything in Qualtrics, and no
distribution can be sent. A survey is a live instrument during fielding — a mistaken write
is not recoverable by an undo.

## Shape

Auth: `datacenter` (`fra1`, or a pasted host/URL) + `api_token`, validated on connect with
`GET /API/v3/whoami`, showing the account name back.

`base_url()` refuses any host that isn't `*.qualtrics.com` with valid DNS labels. The
token travels in an `X-API-TOKEN` header on every call, so a typo must fail loudly rather
than send it somewhere. The same check gates `nextPage` before paging follows it.

`qualtrics_get_survey` returns a summary, not the raw payload: the raw one carries the
flow, blocks and display logic (tens of thousands of tokens on a long survey). It keeps
the questions, their choices, and — the point — `exportColumnMap` resolved to
`Q4_1 → "How satisfied were you with… — Speed of setup"`. Without that, an export is a
grid of numbers and any summary written from it is a guess.

`qualtrics_export_responses` runs the three-step API flow (start → poll `progressId` →
download `fileId`), unzips it (members reduced to their basename — an archive does not get
to choose a path on this disk), and saves into the session's primary root without
clobbering an existing file. `fmt="spss"` lands a real `.sav`, which is what makes the
labels survive into the analysis tools.

## Not in v1

Creating or updating surveys, activating them, sending distributions, and XM Directory
contacts. All are writes against live fieldwork, and none were asked for.

## Tests

`tests/test_qualtrics.py` — base-URL refusal, paging that won't follow an off-host
`nextPage`, questionnaire summarization and the column codebook, zip-slip, the full export
flow (start/poll/download/save, no-clobber, timeout, failure, unknown format, read-only
folder), and the approval line: export asks, reads don't.
