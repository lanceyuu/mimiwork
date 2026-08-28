# AgentHarness review (2026-08-28)

Owner ask: same treatment as FrontierAgent for github.com/ApodexAI/AgentHarness
("i want mimiwork to be really nice to use"). Apache-2.0, 15k lines — it is the
benchmark/evaluation harness that preceded FrontierAgent, so most of its agent
loop was already reviewed in the FrontierAgent pass.

## Taken (adapted, not copied)

Its `react_base/observers/` watch for three loop failure modes and fix them by
popping history and RE-SAMPLING the model. Right for benchmarks (accuracy is
everything, compute is theirs); wrong for MimiWork (every extra model call bills
the user). The two transferable insights landed at the TOOL layer instead,
where recovery is free:

* **Duplicate query** (`duplicate_query_rollback`): `web_search` now remembers
  the session's queries; an exact re-issue returns the cached results plus a
  "these are the SAME results — vary the terms or web_fetch a hit" note. No
  network hit, no duplicate context, no extra model call.
* **Dead query anchoring** (`empty_search_rollback`): an empty result used to
  be a bare `results: []`, which anchors the model on variants of the same dead
  query. It now carries explicit change-course guidance. Not cached, so a
  transient empty stays retryable.

## Considered, not taken

* **Refusal rollback** — targets small fine-tuned models emitting "I'm sorry"
  mid-loop; the models MimiWork serves rarely do, and the fix costs a resample.
* **Tool-call arg normalizer** — reverses an SGLang-specific stringification of
  list args; MimiWork's providers don't exhibit it. Revisit if a provider does.
* **Multi-query `web_search` batches** (`q: list[str]`) — real round-trip savings
  for deep research; deferred as a schema change worth its own pass.
* **Subprocess-isolated benchmark runner** — good engineering, no MimiWork use.
