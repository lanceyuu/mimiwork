# Study Architecture & the Evidence Bar (for drafting and for diagnosis)

Use this for Job B (design the study package) and Job C (diagnose whether the evidence will survive
review). The standard hardened across 2019→2023; what passed in 2019 may not now.

## 1. How many studies, and what each is for

- **5 studies is the floor; 8–12 is the 2022–23 norm.** More studies buy latitude on any single
  study's imperfection. But quantity never substitutes for a mechanism — 8 studies of a main effect
  still fail.
- Each study should do *one* job in the arc: focal effect → mediation → manipulation-of-mediator →
  boundary → rule-out-rival → real-behavior replication. If two studies make the same point, cut one
  or move it to the web appendix.

## 2. The mechanism-evidence ladder (the single biggest lever)

Reviewers now read mechanism claims skeptically. Climb as high as feasible:

1. **Measured mediation (Hayes PROCESS, bootstrapped).** *Table stakes — necessary, not a defense.*
2. **Moderation-of-process** — experimentally manipulate the mediator (or a variable that toggles
   it) and show the effect tracks it. This is the rung that most often separates "good" from "great."
3. **Experimental causal chain** (Spencer, Zanna & Fong) — one study shows X→M, another M→Y.
4. **Competing-mediator / dedicated rule-outs** — a study whose job is to kill the most plausible
   alternative account (the corpus norm rules out 3–9 named rivals).
5. **Heterogeneity-robust mediation** — since BAHM (Dyachenko 2023) showed aggregate PROCESS
   disagrees with individual-level conclusions in ~30% of published studies, reviewers increasingly
   want evidence the mediation holds at the individual level, not just on average.

Rule of thumb: if the entire mechanism case rests on rung 1, expect a "mechanism not established"
rejection. Get to rung 2 or 3.

## 3. Dependent variables — make them consequential

- **At least one real behavioral DV is near-mandatory:** actual choice, purchase, food consumption,
  incentive-compatible bids/WTP, donations, click-through, field/archival behavior.
- Self-reported attitude/intention is **supplemental**, never the sole evidentiary base.
- **MTurk-/Prolific-only packages read as preliminary.** Mix sources (lab, panel, field) and report
  attention checks/exclusions transparently.

## 4. Field-first (the credibility multiplier)

Where possible, anchor the phenomenon in **large-scale archival/field data** before the lab studies
(scanner/loyalty panels, platform data, Google Trends, finance-app transactions, registry data,
retailer field experiments). The field result establishes external validity and *reality*; the lab
isolates the mechanism. The two must connect — the field effect is the experiments' target.

## 5. Open-science expectations (2021+)

- **Pre-registration** (OSF/AsPredicted) shifted from differentiator to near-norm; absence now
  invites a "why not pre-registered?" question. Pre-register the confirmatory studies.
- **Open data and materials** are expected; a web appendix carries supplementary studies, full
  measures, and robustness checks.
- Report **sensitivity/power** and exclusion rules up front.

## 6. Ruling out alternatives — in studies, not footnotes

The corpus norm is a **dedicated study** that experimentally eliminates the most likely rival
account (not a sentence asserting it away). List the 2–3 rivals a reviewer will raise; design a
study that kills each. This is often the difference between "revise" and "reject."

## 7. Common evidence rejections → fixes (diagnosis aid)

| Reviewer verdict | Means | Fix |
|---|---|---|
| "Mechanism not established" | Only measured mediation | Add manipulation-of-mediator or a causal chain |
| "Alternative explanation" | A rival account is open | A dedicated rule-out study |
| "Demand effects / self-report only" | No consequential DV | Add a real-behavior study; reduce transparency of intent |
| "Doesn't generalize" | One population/context | Replicate across samples (incl. non-WEIRD), add field data |
| "Effect could be noise" | Underpowered / no pre-reg | Pre-register, power up, report sensitivity |
| "Where are the boundaries?" | No moderator | Add a theory-predicted moderator that *is* mechanism evidence |

## 8. Boundary conditions

State the **When/Where/Who.** The best boundary conditions are not afterthoughts — they are the
*mechanism evidence*: a moderator that attenuates or reverses the effect because it switches the
mediator on or off. A claim with no boundary reads as overclaiming.
