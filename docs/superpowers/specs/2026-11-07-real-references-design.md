# Real references — design

Date: 2026-11-07 · Owner: Shubin Yu · Status: approved design, not built

## Why

A made-up reference is the fastest way an AI tool loses an academic's trust, and MimiWork
has nothing that guards against it. Today Mimi can only search the general web
(`web_search`, DuckDuckGo by default). There is no scholarly search, no way to check a
reference list, and no reference manager. The universal "Facts" rule in `agent.py`
(`_REPLY_GUIDANCE`) already forbids inventing a DOI or citation, but gives the model no
tool that returns real ones.

This round adds two parts, built and committed in this order:

- **A. Mimi cites real papers.** Two read-only tools that look papers up in OpenAlex and
  Crossref and format a reference from its DOI.
- **B. Check references.** A panel that checks every entry in a Word or PDF reference
  list and writes the few fixes that are safe into the Word file as tracked changes.

Zotero, in-text citation matching, claim checking and `.bib` checking are later rounds.

The guiding rule for B: **the panel must never call a real paper wrong, and never make an
entry worse.** When in doubt it says "couldn't check", verifies without a fix, or shows a
suggestion the researcher applies by hand.

## What the live services showed (probed 2026-11-07)

The plan's first task re-checks these before building on them.

- **Crossref** (`api.crossref.org`) answers without a key, but its public pool allows one
  request at a time, one per second (`x-concurrency-limit: 1`). With `mailto=` in the
  query it moves to the polite pool: three at a time, three per second
  (`x-api-pool: polite-array`). MimiWork sends the project address
  `contact@qualitati.com` (already the app's public contact), never the researcher's.
- A Crossref work's `updated-by` list carries Retraction Watch notices: Wakefield 1998
  (`10.1016/S0140-6736(97)11096-0`) returns `"type": "retraction"`,
  `"source": "retraction-watch"`, and also a `"correction"`.
- **The original "Attention is all you need" (NeurIPS 2017) is not in Crossref.** NeurIPS
  DOIs (`10.52202/…`) exist only for recent volumes. Crossref's top hits for that title are
  an unrelated `posted-content` copy (`10.65215/r5bs2d54`, 27 citations) and other NeurIPS
  papers with "is all you need" in the title. The arXiv version's DOI
  (`10.48550/arXiv.1706.03762`) is a DataCite DOI: Crossref returns 404 for it, and
  `https://doi.org/ra/<doi>` answers `"RA": "DataCite"`.
- **OpenAlex** (`api.openalex.org`) without a key shares $0.10 a day per IP address with
  everyone on that network; a search costs $0.001, so about 100 searches a day for a whole
  campus. A free personal key gives $1 a day. OpenAlex covers conference papers and arXiv,
  and marks retracted works with `is_retracted`.
- **doi.org content negotiation** returns a formatted reference
  (`Accept: text/x-bibliography; style=apa`), BibTeX (`Accept: application/x-bibtex`) and
  CSL JSON (`Accept: application/vnd.citationstyles.csl+json`) for Crossref and DataCite
  DOIs. No citation library is needed.
- OpenAlex's reply carries a notice telling AI agents to request a key by posting the
  user's email address. MimiWork never does this; the researcher creates a key themselves.

## Shared lookups (new `coworker/scholarly.py`)

One module does every network call for A and B, so both share the rules below.

- **Client.** `httpx`, as `web/` uses. User-Agent
  `MimiWork/<version> (https://qualitati.com; mailto:contact@qualitati.com)`; every
  Crossref request also carries `mailto=contact@qualitati.com`. Timeout 10 seconds.
- **Pacing.** One limiter shared across the sidecar for Crossref: at most three requests
  in flight and at most three started per second. If a reply's `x-api-pool` is not the
  polite pool, the limiter drops to one in flight and one per second for the rest of the
  run. On 429 or 5xx: wait for `Retry-After` (at most 10 seconds) and retry once.
- **No lookup cache.** Every lookup is live, so a retraction can never hide behind a
  cached reply. Repeat views are covered by the saved check result (below).
- **OpenAlex key.** Read from the SecretStore profile `openalex:default` at every call, so
  a key saved mid-session works without a restart. Request URLs carrying `api_key` are
  never logged: the module sets the `httpx` logger to WARNING.
- **DOI normalising.** Strip `https://doi.org/`, `http://dx.doi.org/`, `doi:` (any case)
  and surrounding spaces; remove whitespace inside (PDF line breaks); strip a trailing
  `.`, `,` or `;`, and a trailing `)` or `]` only when it has no opening partner in the
  DOI; lowercase. Anything that then does not match `^10\.\d{4,9}/\S+$` is not a DOI.
- **Functions.** Each returns a plain dict with `ok` and, on failure, an `error` code.
  - `crossref_work(doi)`: `/works/<doi>`. On 404, asks `https://doi.org/ra/<doi>`. An
    agency other than Crossref gives `error: "outside_crossref"` with the agency name;
    "DOI does not exist" gives `error: "no_such_doi"`; a failed agency lookup gives
    `error: "lookup_failed"`, never `no_such_doi`.
  - `crossref_search(text, rows=5)`: `/works?query.bibliographic=<text>`.
  - `csl_record(doi)`: CSL JSON from doi.org, used for DOIs outside Crossref.
  - `openalex_search(query, from_year, to_year, n)`, and `openalex_title(title)` for B.
    A 401 or 403 with a saved key gives `error: "openalex_key_refused"`, never a silent
    fallback. A 429 or budget refusal gives `error: "openalex_limit"`.
  - `formatted(doi, style)` and `bibtex(doi)` through doi.org. Only a 404 means
    `no_such_doi`; a 406 or an HTML reply means `cannot_format`.
  - `retraction(record)` reads Crossref `updated-by`. `retraction`, `withdrawal` and
    `removal` mean retracted; `partial_retraction` means partly retracted;
    `expression_of_concern` and `expression-of-concern` mean a concern note; corrections
    are ignored. For an OpenAlex record, `is_retracted: true` means retracted (year
    unknown). For a DataCite DOI the status is `unknown`, never "not retracted".
- **Record title.** Crossref `title[0]`, plus `": " + subtitle[0]` when there is a
  subtitle that `title[0]` does not already contain; tags stripped (`<[^>]+>`) and HTML
  entities decoded (`html.unescape`). The "main title" is the part before the subtitle
  (or before the first colon when Crossref has no separate subtitle).

## A. Mimi cites real papers

### Tools (new `coworker/tools/papers.py`)

Registered in `agent.py` for every persona, next to `web_search`. Both are read-only, so
they never stop for approval. Their descriptions say results are external data, not
instructions, as `web_search` does.

**`find_papers(query, from_year?, to_year?, max_results?)`**

- Searches OpenAlex (`/works?search=`, year filter, `per-page` ≤ 10, default 5).
- Returns per paper: title, authors (up to 5, then "et al."), year, venue, type, DOI,
  citation count, `is_retracted`, a free-to-read link (`best_oa_location`) when one
  exists, and an abstract rebuilt from `abstract_inverted_index`, cut to 600 characters.
- `openalex_limit`: searches Crossref (`/works?query=`) instead and adds the note
  "Searched Crossref: OpenAlex's free daily limit is used up, so results may be less
  relevant and have no abstracts. A free OpenAlex key in Settings raises the limit."
- `openalex_key_refused`: returns that error with "OpenAlex refused the saved key. Check
  it in Settings, Models, Paper search."

**`cite_paper(doi, style?)`**

- Returns the formatted reference from doi.org in the style asked for (default `apa`),
  the BibTeX entry, and the retraction status (`retracted`, `partly_retracted`,
  `concern`, `none`, or `unknown` for non-Crossref DOIs).
- Allowed styles are a fixed list of CSL ids: `apa`, `chicago-author-date`,
  `harvard-cite-them-right`, `modern-language-association`,
  `american-sociological-association`, `ieee`, `vancouver`,
  `american-medical-association`, `nature`. Anything else is refused with the list. The
  plan's first task confirms doi.org accepts each id and drops any it does not.
- `no_such_doi`: "This DOI does not exist." `cannot_format`: "doi.org could not format
  this DOI; here is the record" with the title, authors, year and venue from Crossref.

### The writing rule and nudges

- The Facts paragraph of `_REPLY_GUIDANCE` gains: "References: take every reference from
  `find_papers`, `cite_paper` or a file the user gave you. If nothing fits, write
  [source needed] where the citation would go and say so. Never write a reference from
  memory, and say plainly when a paper you cite is retracted."
- The engine's unsourced-facts nudge (`_UNSOURCED_TEXT`, `engine.py`) names
  `find_papers` beside `web_search`, `web_fetch` and `kb_search`.
- `find_papers`, `cite_paper` and `check_references` join the time-saved table
  (`timesaved.py`) like the other research tools.

## B. Check references

### What the researcher sees

Word (`.docx`) and PDF previews in the right rail gain two tabs in the viewer header,
**Preview** (the current view, unchanged) and **References**. While References is shown it
replaces the whole `.artifact-preview` element and the pin bar is hidden, so neither the
click-to-pin handler nor the feedback screenshot ever sees it. Pins return with Preview.

Before a check, the tab shows one line ("Mimi reads the reference list and looks up each
entry in Crossref and OpenAlex.") and a **Check references** button. Nothing runs until
the researcher clicks, so opening a file never spends credits. A saved result for this
exact version of the file shows straight away, headed "Checked on 7 November 2026", with a
**Check again** button that re-runs everything live.

After a check:

- A summary line: "42 references: 35 verified, 4 need a fix, 1 not found, 1 retracted,
  1 couldn't be checked." Entries the model could not tie to the file text are counted
  too: "2 entries couldn't be read."
- The groups below, in this order. Each item shows its entry (cut to two lines), its notes
  in plain words, and **Open the record** (`https://doi.org/<DOI>`, or the OpenAlex page
  when there is no DOI) when a record was found.
  - **Retracted** (red): "Retracted in 2010" or "Partly retracted in 2019", with a link to
    the notice ("Retracted (OpenAlex)" when only OpenAlex says so). Any fix on it is shown
    unticked: the researcher should first decide whether to cite it at all.
  - **Needs a fix**: each note, and for each fix either a tick box (a fix Mimi can write)
    or a **suggestion** with **Copy** (one the researcher applies by hand).
  - **Not found**: "Mimi couldn't find this in Crossref or OpenAlex. Books, reports and
    work in some languages are often not listed there." Plus **Search Google Scholar**
    (`https://scholar.google.com/scholar?q=<title>`). Never worded as fake.
  - **Couldn't check**: lookups failed, the entry has no title to look up, or OpenAlex's
    daily limit was reached before this entry. Never counted as not found.
  - **Verified**: folded to a count until opened. Notes show on the item (a concern, a
    one-year difference, "Found on DataCite", "Found on OpenAlex").
- For Word files: **Write N fixes into the Word file**, where N counts ticked fixes.
  Afterwards: "N fixes written as tracked changes. Accept or reject them in Word (Review,
  Track Changes). Check again to confirm." The preview reloads.
- A list made by a citation tool shows, instead of the Write button: "This list is made by
  Zotero. Fix the entries in Zotero, then refresh the bibliography in Word." It names
  Zotero, EndNote, Mendeley, Citavi, Paperpile, RefWorks or Word's own bibliography when it
  can tell, and otherwise says "a citation tool". Every fix is then a suggestion.
- PDFs get the panel with suggestions only; the researcher fixes the source file.

In chat, "check my references" works too: the `check_references(path)` tool runs the same
check (sharing the saved result), returns the counts and every problem, and lists the file
in `files`. It is added to `manager._ARTIFACT_TOOLS` so the file shows among the session's
files. The chat tool never writes fixes; the panel button does, or Mimi uses the existing
`revise_document` if the researcher asks in chat. The panel's sentences live in
`i18n.tsx`; the chat tool renders the same reason codes from an English table in
`refcheck.py` (the model relays them in the researcher's language).

### How a check works (new `coworker/refcheck.py`)

1. **Find the reference list.**
   - **Word.** A reader walks the body in order, including paragraphs inside content
     controls (`w:sdt`), which `_indexed_blocks` skips. Each paragraph carries its
     `_indexed_blocks` index when it has one (direct body paragraphs) and `None` inside a
     content control. Its reading text shows tabs and breaks as spaces (unlike
     `_para_text`). The reader also notes whether the list is managed by a citation tool:
     any `ADDIN` field around it (`ZOTERO_BIBL`, `EN.REFLIST`, `Mendeley Bibliography`,
     `CITAVI`, `PAPERPILE`, `RW.` named when recognised), or a content control holding it
     (Mendeley Cite, Word's Bibliography gallery).
   - **The heading.** The list starts after the last paragraph that, trimmed and with an
     optional leading section number (`7.`, `VII.`) and trailing colon removed, equals one
     of these, case-insensitively: References, Reference, Reference list, Bibliography,
     Works cited, Literature cited, Sources, Literatur, Literaturverzeichnis, Références,
     Bibliographie, Referanser, Litteratur, Litteraturliste, Kilder, Referencias,
     Bibliografía, Bibliografia, Referências, Literatuur, 参考文献, 참고문헌,
     Список литературы, المراجع. It runs to the end, capped at 400 paragraphs. With no
     such heading, the last 300 paragraphs are sent and the model is told there may be no
     list. The model is told to stop at the end of the list (tables, figures and
     appendices often follow it).
   - **PDF.** Page text comes from the same `pypdf` extraction `read_pdf` uses (called
     directly, after the path is resolved through the roots). The heading rule applies
     line by line; a heading repeated at the top of consecutive pages is a running head,
     and the list starts at its first occurrence. With no heading, the last third of the
     pages. Capped at 60,000 characters; when the cap cuts the list, the summary says so.
     A scanned PDF with no text layer is reported as "This PDF is a scan with no text Mimi
     can read," not as "no reference list."
2. **Read it (model calls in batches of up to 60 paragraphs).** The model only splits the
   text into entries and reads their parts. Per entry it returns the entry `text` as
   printed, the first and last paragraph number (Word), and the title, first author's
   surname, year and DOI as printed. Each call uses `max_tokens` 8000 and
   `reasoning_effort="none"`, like the explain call.
   - **Batch seams.** Unless the batch is the last one, its last entry is dropped and the
     next batch starts at that entry's first paragraph, so no entry is split between two
     calls. Two exceptions keep the loop finite: when the last entry starts at the batch's
     own first paragraph, it is kept and the next batch starts after it; when a batch
     returns no entries, the next batch starts a full batch later. The number of calls is
     capped at eight; paragraphs left unread when the cap is hit are counted as "not
     checked" in the summary. A kept entry that runs past its batch's end is rare and is
     caught by the entry text check (it is then counted as "couldn't be read").
   - **The loose form.** For every comparison of model output with file text: NFKC, case
     folded, curly quotes made straight, every dash, hyphen and minus removed (so PDF
     line-end hyphenation and "self-regulation" compare equal), all whitespace collapsed
     to one space.
   - **Entry text check.** The entry's loose form must appear in the loose form of the
     paragraphs it names (Word) or of the page text (PDF). Otherwise the entry is dropped
     and counted as "couldn't be read". The model's copy only locates the entry; for Word,
     everything after this point uses the file's own paragraph text.
   - **Field checks.** The DOI must appear in the entry text lowercased with whitespace
     removed; the year (digits, a trailing letter such as `2017a` allowed) must appear in
     the entry text; the surname and at least 90% of the title's words must appear in its
     loose form. A field that fails is discarded, so a DOI or title the model filled in
     from memory never drives a verdict.
   - Zero entries: "Mimi couldn't find a reference list in this file." At most 300
     entries; any beyond are counted as not checked.
3. **Look each entry up (code only).**
   - **Printed DOI:** `crossref_work(doi)`.
     - `outside_crossref`: `csl_record(doi)` and the same-paper test below. Same paper:
       Verified with the note "Found on DataCite" (the agency named), retraction status
       unknown. Not the same paper: the printed DOI is wrong (below). A failed
       `csl_record` gives `lookup_failed`.
     - **A book's DOI on a chapter.** Checked only after the printed DOI's record has
       failed the title test. When that record is a book type
       (`book`, `edited-book`, `monograph`, `reference-book`) and at least 90% of its
       title's words appear in the entry's loose form, the DOI is the containing book's.
       That is a defensible reference: no DOI verdict, and the chapter is checked by
       search as usual (a chapter DOI found there is offered as a suggestion only).
     - `no_such_doi`, or a Crossref record that fails the **title** test: the printed DOI
       is wrong; search as below. A record that passes the title test but fails only the
       author test (some records have no authors, some works have two DOIs) is accepted
       as the same paper.
   - **Search:** `crossref_search(entry text)`, unless a printed DOI already matched.
   - **OpenAlex fallback:** no Crossref record qualifies and the entry has a title:
     `openalex_title(title)`. For the author test, a surname matches an OpenAlex author
     when it equals the last word of `display_name` (after normalising) or any of its
     words. `openalex_limit` puts the entry in Couldn't check.
4. **Is it the same paper?** Normalising for matching is Unicode-aware: NFKC, case folded,
   accents stripped (NFKD minus combining marks), every character that is not a letter or
   digit in any script (`str.isalnum`) turned into a space, spaces collapsed. An empty
   normalised title never matches anything; an entry with no usable title goes to
   Couldn't check ("no title to look up").
   - **Title test.** The full record title against the full entry title has a
     `SequenceMatcher` ratio of at least 0.9. Failing that, the main titles may be
     compared (record main title against the entry title's part before its first colon),
     but only when one side has no subtitle: two different subtitles under the same main
     title ("Brand love: Antecedents…" and "Brand love: Consequences…") are two papers.
   - **Author test.** The entry's first surname has a ratio of at least 0.85 with the
     record's first author's family name, or equals the family or given name of any
     record author (names stored in swapped order). A record with no authors passes only
     with a title ratio of at least 0.95 and a year within one.
   - A record is the same paper when both tests pass. When the title pair that matched has
     three normalised words or fewer ("Editorial", "Reply", "Introduction"), it also needs
     an exact surname and a year within one.
   - When several records qualify, they are ranked by: full-title match before main-title
     match, then the higher title ratio, then `d` ≤ 1 (below), then published type, then
     the higher `is-referenced-by-count`. How well a record matches always outranks how
     often it is cited. **Published types** are `journal-article`,
     `proceedings-article`, `book`, `book-chapter`, `monograph`, `edited-book`,
     `reference-book` and `report`.
5. **Decide the verdict (code only).**
   - **Year distance.** `d` is the smallest absolute difference between the entry's year
     (trailing letter dropped) and the years of the record's `issued`, `published-print`
     and `published-online`. No year comparison for "n.d.", "in press", "forthcoming" or a
     missing year.
   - **A fix may only come from a published-type Crossref record.** A `posted-content`
     copy, an OpenAlex record or a DataCite record can verify that a paper exists, never
     supply a correction. This is the guard against the Vaswani copy.
   - **The codes.** One table, used by the panel and the chat tool. "Write" means Mimi can
     write the fix; "Suggest" means it shows the corrected text with Copy.

   | Code | Group | Fix | Default | When |
   |---|---|---|---|---|
   | `retracted` (year, notice DOI) | Retracted | none | n/a | `updated-by` retraction, withdrawal or removal; or OpenAlex `is_retracted` |
   | `partly_retracted` (year, notice DOI) | Retracted | none | n/a | `partial_retraction` |
   | `doi_other_paper` (that paper's title) | Needs a fix | Write: replace the DOI | ticked | printed DOI is wrong (other paper), right published record found |
   | `doi_not_found` | Needs a fix | Write: replace the DOI | ticked | printed DOI does not exist, right published record found |
   | `doi_unfixable` (that paper's title, if any) | Needs a fix | none | n/a | printed DOI is wrong, and the entry matched only a copy, an OpenAlex or a DataCite record, so nothing can supply the right DOI (with no match at all it is `not_found`) |
   | `doi_missing` | Needs a fix | Write: add the DOI | ticked | no DOI printed (and no `10.` DOI pattern anywhere in the entry), the matched record is published-type, and at least half of the matched entries print a DOI |
   | `surname_differs` (record surname) | Needs a fix | Write: replace the surname | ticked | surname ratio 0.85 to below 1 with the record's first author, and equal to no author's given or family name (a different author order is not a misspelling) |
   | `title_differs` (record title) | Needs a fix | Suggest | n/a | the title pair that passed has a ratio below 0.98 (a main-title-only match never raises it) |
   | `edition` (record years) | Needs a fix | Suggest (for books, a note only) | n/a | `d` > 1 |
   | `year_other_work` (record years, container) | Verified | none, a note | n/a | `d` > 1, the record is not a book, and its journal or book (`container-title`) is not printed in the entry: likely a review of the cited book or another work under its title, so the year is not compared |
   | `year_differs` (record years) | Verified | none, a note | n/a | `d` = 1 ("often a preprint or online-first year") |
   | `concern` (year) | Verified | none, a note | n/a | expression of concern |
   | `outside_crossref` (agency) | Verified | none, a note | n/a | DOI registered elsewhere, same paper |
   | `found_openalex` | Verified | none, a note | n/a | verified through OpenAlex only |
   | `found_copy` | Verified | none, a note ("Found as a preprint or posted version; details not compared with a published record") | n/a | verified only through a non-published-type record |
   | `not_found` (printed-DOI paper title, if any) | Not found | none | n/a | no record qualifies |
   | `lookup_failed`, `no_title`, `openalex_limit` | Couldn't check | none | n/a | as named |

   - An entry with several codes sits in the first group of this order: Retracted, Needs a
     fix, Not found, Couldn't check, Verified.
   - Books for `edition` are `book`, `monograph`, `edited-book` and `reference-book`: a
     different year there usually means a different edition, so only a note is shown.
   - OpenAlex `is_retracted` puts an entry in Retracted only when its first surname equals
     the last word of the matched OpenAlex first author's `display_name`. A false red
     Retracted is the worst mistake the panel can make; a looser OpenAlex match gives a
     `concern`-style note "OpenAlex lists a retracted paper with this title" instead.
6. **The fixes are made by code, not by the model.** Each writable fix is one small,
   exact replacement in the entry's own text:
   - **Replace the DOI.** The printed DOI's `10.…` span (found in the paragraph text,
     case-insensitively) is replaced by the record DOI; any `https://doi.org/` or `doi:`
     before it stays as printed.
   - **Add the DOI.** The record DOI is appended after the entry text, separated by one
     space, in the form most other entries in the list use (`https://doi.org/…` or
     `doi:…`, defaulting to `https://doi.org/…`).
   - **Replace the surname.** The first whole-word, case-insensitive occurrence of the
     printed surname is replaced by the record's family name, in the list's own casing
     (Crossref sometimes stores names in capitals). If no such literal span exists, the
     fix becomes a suggestion.
   - Every fix is a span: start and end offsets in the paragraph's `_para_text` (for
     writable paragraphs this equals the reading text, since they hold no tabs or
     breaks), plus the new text.
   - **Suggestions** (title, edition) show the record's formatted reference from doi.org
     in the detected style (APA when the style is `other`) for the researcher to compare
     and copy. The model writes no fix text at all.
7. **When a fix can be written.** Only in a Word file whose list no citation tool manages,
   and only when the entry fills exactly one direct body paragraph: the entry's loose form
   equals the loose form of that paragraph's whole text, and no other entry shares the
   paragraph. That paragraph must also pass the writer's own word-level test (below), so
   the tracked change touches only the replaced words and keeps the formatting. Otherwise
   the fix becomes a suggestion, with the reason ("This entry has a link or layout Mimi
   can't edit safely. Copy the fix into Word.").
8. **Save the result** under `state_dir()/refcheck/<sha256 of the file bytes>.json`: the
   file hash, the check time, and per entry its id, paragraph index, text, group, codes
   with params, record DOI, title and link, fixes (kind, old span, new text, writable,
   default tick) and suggestions. The model writes nothing the researcher reads, so the
   result does not depend on the app language. Results older than 90 days are deleted
   when the sidecar starts.
9. **One check per file at a time.** A lock per file hash makes a panel click and the chat
   tool share one run instead of paying twice.

### Writing the fixes

- Route `POST /v1/sessions/{id}/artifacts/references/apply` with `path` and the ticked fix
  ids. It refuses, writing nothing:
  - a path whose folder is read-only (resolved through `resolve_write`, as tool writes
    are);
  - while the session is in the middle of a turn: "Wait until Mimi has finished, then try
    again.";
  - a file whose hash no longer equals the checked hash: "The file changed since the
    check. Check again.";
  - a list managed by a citation tool, or a fix not marked writable;
  - a file Word has open (a `~$…` lock file beside it whose name, after the `~$`, is the
    end of the file's name; Word shortens long names differently from short ones): "Close
    the file in Word first, or Word will overwrite the fixes when it saves. If Word is
    closed, open and close the file once to clear the leftover lock."
- **Mid-turn guard without a race.** The route takes the session's running mark
  (`manager.try_mark_running`) for the whole write and releases it with `release_run_claim` (not `mark_idle`, which rings the "finished" bell), so a
  chat turn cannot start between the check and the write. If the mark is taken, it
  refuses with the "wait" message.
- **Several fixes on one paragraph** (a surname and a DOI) are grouped: their spans are
  applied right to left to the original `_para_text`, giving one edit per paragraph, so
  no fix undoes another.
- **One tracked-change writer.** The body of `revise_document` becomes a module-level
  function in `docx_tools.py`, `apply_tracked_revisions(target, edits)`, which the tool
  and this route both call. The condition under which `_track_replacement` today takes its
  word-level path (every live run a direct child of the paragraph or of `w:ins`, every run
  holding only `w:rPr` and `w:t`, the runs' text equal to `_para_text`, and `_word_ops`
  finding a shared word) moves into `word_level_ok(para, new_text)`. Step 7 calls it, so
  "writable" means exactly "the writer will not fall back to replacing the paragraph". A
  `# ponytail:` comment on it names the ceiling and the upgrade: entries with links, tabs
  or symbols are suggestion-only until `_track_replacement` handles runs inside
  `w:hyperlink`, `w:smartTag`, `w:fldSimple` and `w:customXml`, and keeps tabs.
- Each change's reason is a plain sentence ("Corrected the DOI to match the Crossref
  record.").
- **Undo.** Before writing, the route calls the session engine's
  `file_recovery.begin_turn()` and then `capture("revise_document", {"path": path})`, so
  the panel write gets its own Undo point instead of joining an earlier turn.
- The new file has a new hash, so the panel then shows the "Check again to confirm" state.

### Routes and errors

- `POST /v1/sessions/{id}/artifacts/references` with `path`, `cached_only` and `fresh`
  (Check again). A sync `def` route like the explain route, so the threadpool runs it.
  It accepts only paths ending in `.docx` or `.pdf` (`_artifact_kind` reports Word files
  as `office`) and refuses a session with no engine ("this conversation has no folder").
  A failed model call: "Couldn't read the reference list. Try again." An 80-entry list
  needs about 100 to 160 lookups at three a second, so about a minute with the model
  calls; the button shows "Checking references…".
- `GET`/`POST /v1/scholarly`: `GET` returns only `has_key`, never the key. `POST` with
  `api_key` saves it as `openalex:default`; an empty `api_key` removes it.
- `check_references` makes model calls, so it is built in `agent.py` with
  `provider=provider, model=model`, the way `explorer_tools` is, and registered for every
  persona that has a workspace. It reads only through the session's roots.

### Settings

A **Paper search** card in Settings, Models (where the other keys live, "stored only on
this computer"): an OpenAlex key field, Save, Remove, and a status line ("Using your
OpenAlex key." / "No key: a small free daily limit shared with your network. Paper
searches and reference checks both use it."), with a link to
`https://openalex.org/settings/api` to create one.

### Words on screen

All new panel and Settings strings go into `src/i18n.tsx` in the nine languages, as in
the code view. Reason codes map to sentences there.

## Privacy

- Crossref and doi.org receive reference entries and DOIs only, which are public
  bibliographic data. OpenAlex receives search queries and titles. The model receives the
  reference section, not the rest of the document.
- Requests identify as MimiWork with the project contact `contact@qualitati.com`. No user
  email address is ever sent.
- All lookups are reads, so nothing here is approval-gated. Writing fixes needs the
  researcher's click, lands as tracked changes they can reject, and has an Undo point.

## Out of scope

Zotero; in-text citations versus the list; whether a cited paper supports the claim;
`.bib` files; reformatting a whole list into another style; fixing titles or years in the
file (shown as suggestions); several reference lists in one file (only the last is
checked); routing OpenAlex through the QualiTaTi gateway (possible later if per-user keys
prove a hurdle).

## Testing

- **Backend (pytest, no network).** A fake transport serves recorded Crossref, OpenAlex and
  doi.org replies.
  - Lookups: polite-pool `mailto` on every Crossref call; at most three in flight and
    three a second; the limiter drops to one when the pool is not polite; `Retry-After`
    honoured; DOI normalising (prefixes, trailing period, balanced and unbalanced
    brackets, PDF line break); 404 then DataCite gives `outside_crossref`; a failed agency
    lookup is `lookup_failed`; a refused OpenAlex key is an error, not a fallback; no
    `api_key` in logs.
  - Matching: exact; subtitle left out (no `title_differs`); Crossref subtitle and markup;
    misspelled first author; swapped Chinese name; a CJK title; an empty title never
    matches; a generic short title needs surname and year; a record with no authors; a
    second DOI for the same work is not called wrong; the Vaswani copy verifies as
    `found_copy` and never supplies a DOI; a third-edition book against a first-edition
    record gives an `edition` note only; two papers sharing a main title with different
    subtitles do not match; the exact record outranks a more-cited sibling; a chapter
    printed with its book's DOI is not called wrong.
  - Verdicts: every row of the table, including group placement when an entry has several
    codes; `doi_missing` only when half the list prints DOIs and never when a `10.`
    pattern is present; network failure gives Couldn't check; OpenAlex `is_retracted`
    gives Retracted.
  - Reading: headings with numbers and in several languages; a PDF running head; the cap
    note; content-control lists found and marked managed; an `ADDIN` field marks the list
    managed; curly quotes, dashes, ligatures and PDF hyphenation pass the loose check;
    entry text not in the file is dropped and counted; a model-supplied DOI not in the
    entry is discarded; an entry across a batch seam is read once, whole; the final
    batch keeps its last entry; a batch whose only entry starts at its first paragraph,
    or a batch with no entries, still moves forward, and calls stop at eight with the rest
    counted as not checked.
  - Fixes: DOI replaced keeping its prefix; DOI added in the list's own form; first
    surname occurrence replaced; an entry sharing a paragraph, spanning two paragraphs, or
    holding a link or tab is suggestion-only.
  - Apply: changed file refused; read-only folder refused; mid-turn refused and the
    running mark held during the write; Word lock file refused; managed list refused;
    Undo point is its own turn; a surname and a DOI fix on one paragraph both land;
    tracked changes land on the right words; the refactored `revise_document` passes its existing tests unchanged.
  - Tools: `find_papers` falls back to Crossref on the limit with the note; the key is read
    at call time; `cite_paper` refuses an unknown style and reports `unknown` retraction
    status for a DataCite DOI.
  - Saved result and lock: a second check of the same file without Check again makes no
    model or network call; two simultaneous checks make one run.
- **GUI (vitest).** The References tab: button before a check; "Checked on" date; groups in
  order; Verified folded; ticks follow the table; Write sends only ticked, writable ids;
  Copy on suggestions; managed-list message; "file changed" and "wait" messages; PDFs have
  no Write button; clicks in the References tab open no pin draft and the pin bar is
  hidden. The Settings card never shows the key and can remove it.
- **e2e (Playwright).** Screenshot the References tab with mocked results on a Word file,
  waiting out the 0.15-second button transition before the shot.
- **Live check (manual, not CI).** One script runs a real reference list (including
  Wakefield 1998, the Vaswani paper, an arXiv DOI and a book) against the live services
  before release, and prints each verdict.
