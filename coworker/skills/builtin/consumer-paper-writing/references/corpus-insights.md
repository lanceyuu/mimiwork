# What Gets Published in JCR — Patterns from 280 Articles (2019–2023)

Empirical synthesis of every article in the corpus (vols. 45–50, 2019–2023), coded for
contribution, theory move, mechanism evidence, study architecture, and positioning. Use this as
the *evidence base* behind every recommendation in this skill. Claims here are corpus-grounded;
exemplars are cited as Author (year). When you tell a user "JCR expects X," it is because X
recurs across the cohort — not a guess.

## Contents
1. The one-sentence bar
2. Archetype mix (what a "JCR paper" actually is)
3. The contribution signature: the qualified reversal
4. The dominant theory move: borrow a lens for a mechanism
5. New constructs that travel
6. Mechanism evidence — the hardening standard
7. Study architecture & data (incl. "field-first")
8. Positioning, timeliness, the "interesting" hooks
9. CCT / qualitative: process theorizing, not description
10. Conceptual / framework papers: reorder, don't review
11. Transferable techniques worth naming
12. Rising territories (2022–2023)
13. The self-check before submission

---

## 1. The one-sentence bar

> A JCR paper shows a **novel, mechanism-based "why"** that **overturns a belief the audience
> holds**, proven with **converging, often consequential, evidence** and **bounded by conditions**.

Every section below is a facet of that sentence. The two failure modes the corpus almost never
tolerates: (a) a **main effect with no mechanism** ("X relates to Y"), and (b) a **mechanism with
no surprise** ("we confirm the obvious"). You need both the *why* and the *tension*.

## 2. Archetype mix — what a "JCR paper" actually is

Across 280 papers: **~62% quant-experimental, ~15% CCT/qualitative, ~13% conceptual/curation,
~10% mixed (big-data/field + experiments)**, plus a few methods/meta-analysis pieces. Implications:

- The default JCR paper is a **multi-study experimental package built around a mediator.** If a
  user is writing one, the rest of this guide is the spine.
- CCT and conceptual papers are a real and respected minority — but each has its *own* bar
  (§9, §10). Don't apply experimental criteria to them or vice versa.
- The **mixed "field + lab" type is the fastest-growing and highest-prestige** (§7).

## 3. The contribution signature: the qualified reversal

The single most recurring publishable structure (Group 1 alone: ≥18 of 47) is the **qualified
reversal / crossover**:

> "X is believed to produce Y. We show X produces **not-Y** — under condition C / for people A /
> at stage S — *because* of mechanism M."

- Naked main effects ("X increases Y") are nearly absent at the top. The **crossover interaction**
  or **stage-dependent flip** is what reads as a contribution.
- Reversal must be **surprising *and* theoretically inevitable.** An arbitrary flip dies; a flip
  that the mechanism makes obvious-in-hindsight lands. The mechanism is what licenses the surprise.
- Common surface form: the **"curse of a good thing"** — something assumed beneficial backfires:
  heritage branding hurting line extensions (Han 2021), high emotional intelligence enabling fraud
  (Hasford 2022), God salience lowering self-improvement interest (Grewal 2022), busyness *raising*
  self-control (Kim 2019), luxury producing impostor feelings (Goor/Sterling 2020).
- Map this to Davis's "interesting" types: most JCR hooks are **co-variation flips** (assumed
  positive is negative), **function reversals** (assumed-effective is ineffective), or
  **opposition** (seeming-similar are opposite). See `making-contributions-interesting.md` in the
  theory-building skill.

## 4. The dominant theory move: borrow a lens for a mechanism

~90% of papers **import a lens from an adjacent discipline** and use it to generate a prediction
neither home literature could. The borrow is almost never cosmetic — **its payload is the
mechanism.**

Donor disciplines, by frequency:
- **Social/cognitive psychology** (dominant): sociometer, self-verification, construal level,
  attribution, fuzzy-trace, attention/scope, mind perception, dual-process.
- **Sociology / critical theory** (esp. CCT): assemblage theory (Deleuze/DeLanda), institutional
  theory, racial formation, Giddens' ontological security, Rosa's acceleration, Foucauldian
  governmentality, liquid modernity.
- **Evolutionary / biological**: behavioral immune system / disease avoidance (Huang 2020, Galoni
  2020), mate signaling (Chen 2023).
- **Linguistics / computational**: speech-act theory, NLP sentiment/embeddings (the "mixed" type).
- **Natural science as analogy**: thermodynamics/entropy (Biliciler 2022), antifragility (Dietrich
  2021).

Coaching consequence: when a user's theory feels thin, the highest-leverage question is **"whose
mechanism are you borrowing, and does it predict something your home literature can't?"** A model
that only recombines home-field constructs rarely clears the bar.

## 5. New constructs that travel

~half of papers (both quant and CCT) introduce a **named construct.** The ones that get cited share
four properties — use as a checklist:
1. **Precisely scoped** (you can say what is and isn't an instance).
2. **Memorably named** — "tangential immersion" (Lieberman 2022), "found time" (Chung 2023),
   "magnitude heuristic" (Daniels 2023), "status pivoting" (Goor 2021), "budget depreciation"
   (Choe 2021), "dysplacement" (Grant 2023), "affordance misalignment" (Mardon 2023).
3. **Tied to one testable mechanism** (not a vague umbrella).
4. **Bounded** by a stated condition.

A construct that is just a relabel of an existing one, or a name with no mechanism, is a red flag.

## 6. Mechanism evidence — the hardening standard

This is where the bar rose most across 2019→2023. Treat as a ladder:

- **Table stakes (necessary, not sufficient):** Hayes PROCESS bootstrapped mediation; manipulation
  checks; a measured mediator.
- **What separates "good" from "great":**
  - **Moderation-of-process** — experimentally *manipulate the mediator* (or a variable that
    switches it on/off) and show the effect moves accordingly.
  - **Experimental causal chain** (Spencer, Zanna & Fong) — separate studies establishing
    X→M and M→Y.
  - **Competing-mediator / alternative-account studies** — dedicated studies ruling out 3–9 named
    rivals (the corpus norm; e.g., Jami 2021 rules out five).
  - **Moderated mediation** with a theory-predicted moderator that *is* the mechanism evidence.
- **The 2021+ overlay:** **pre-registration** (OSF/AsPredicted) shifted from differentiator to
  near-norm; open data/materials expected. The **BAHM paper (Dyachenko 2023)** showed aggregate
  PROCESS conclusions disagree with individual-level ones in ~30% of published studies — so
  reviewers increasingly want **heterogeneity-robust** mechanism evidence, not a single mediation.

Coaching consequence: "we ran a PROCESS mediation" is no longer a mechanism *defense.* Push users
toward at least one **manipulation of the mediator** or a **causal-chain** design.

## 7. Study architecture & data

- **Study count:** 5 is the floor; **8–12 is the 2022–23 norm**; outliers run far more (Jia 2023,
  star-vs-bar ratings, ~30 studies, N≈18k). More studies buy latitude on any single study's
  imperfections.
- **Consequential DVs are near-mandatory.** At least one study with **real behavior** — actual
  purchase/choice, food consumption, incentive-compatible bids, click-through, donations, archival
  records. Self-report intention is supplemental, never the sole base. **MTurk-only packages read
  as preliminary.**
- **The prestige architecture is "field-first, mechanism-later":** open with **large-scale
  archival/field data** to establish the phenomenon's reality and external validity (scanner
  panels, Kickstarter, Rotten Tomatoes, Google Trends, personal-finance-app transactions,
  blood-drive/registry data, retailer field experiments), **then lab experiments to isolate the
  causal mechanism.** This hybrid is displacing the pure multi-study-MTurk package at the top tier
  (≈1/3 of recent quant papers). The "mixed" archetype's **NLP-on-text + confirmatory experiments**
  is a standardizing template for language/behavior work.
- Samples increasingly **non-WEIRD** and treated as generalizability evidence, aligned with the
  editorial DEI turn (Arsel 2022 curation; Schmitt 2021 editorial).

## 8. Positioning, timeliness, and the "interesting" hooks

- **Strongest positioning = reconciliation or problematization, not gap-spotting.** The most
  efficient line is **"we resolve a puzzle/contradiction that has frustrated the field"** or
  **"the literature assumes X; we show not-X."** Pure "X has not been studied" rarely carries a
  top paper. (See Locke & Golden-Biddle and Alvesson & Sandberg in the theory-building skill.)
- **Timeliness is foregrounded in sentence 1**, not buried in closing implications: COVID/threat
  (Campbell 2020), AI and autonomous vehicles (Longoni 2019, Gill 2020, Bergner 2023, Castelo
  2023), food waste/sustainability, financial well-being, DEI.
- **Managerial/societal relevance is woven through**, not a tacked-on paragraph — Schmitt's
  "Relevance—Reloaded" (2022) editorial signals this explicitly.

## 9. CCT / qualitative: process theorizing, not description

The qualitative papers that publish share a hardened profile:
- **Deliverable is a named, sequenced process model or a new mid-range construct**, not rich
  description. Examples: pathic stigma (Valor 2021), four-stage "we-ness" (Beverland 2021),
  brand morphogenesis (Molander 2022), consumer deceleration (Husemann 2019), dysplacement
  (Grant 2023), affordance misalignment (Mardon 2023).
- **Extend *and correct* a canonical text** (Belk, Goffman, Holt, Giddens) rather than just adding
  a context.
- **Credibility = depth**: multi-year, multi-source ethnography/netnography (5–7 yr panels) substitutes
  for statistical power.
- **Import a macro social theory** (assemblage, governmentality, social acceleration) as the lens.
- Non-WEIRD/marginalized context as **theoretical leverage**, not exotic color.

## 10. Conceptual / framework papers: reorder, don't review

- Succeed only by **reordering the field**: import a macro theory not yet in consumer research,
  show it **resolves contradictions the incumbent paradigm can't**, and generate a **structured
  research agenda.** Pure summaries don't appear.
- Examples: threat-response tapestry borrowing ontological security (Campbell 2020); consumption
  ideology (Schmitt 2022); racial formation theory (Crockett 2022); choosing-for-others framework
  (Liu 2019).
- **Curations** are invited/editorial; they reconcile prior findings as special cases of a more
  general lens and set an agenda (Keller 2020 branding; Lamberton 2020 ownership; Arsel 2022 DEI).

## 11. Transferable techniques worth naming for users

- **Stage-gated theorizing** — decompose a well-studied process into temporal/contextual stages and
  show the effect *reverses across stages*. High novelty at low cost. Exemplars: novice→enthusiast→
  expert (LaTour 2019); pre- vs post-action guilt (Duke 2019); purchase vs consumption stage;
  preference-construction vs evaluation (Zwebner 2020).
- **Bidirectional moderation** — attenuate *and* amplify the effect from both theoretical sides
  (Zhou 2019), which pins the mechanism harder than one moderator.
- **Differentiate, don't relabel** — when introducing a construct adjacent to an existing one,
  include a study that **empirically separates** them (e.g., busy mindset vs time pressure,
  Kim 2019; verbal vs visual embodiment, Bergner 2023).
- **Rule out rivals in dedicated studies**, not footnotes — a whole study whose job is to kill the
  most likely alternative account.

## 12. Rising territories (2022–2023) — where the editorial appetite is

Platform/digital behavior (fake reviews, influencers, service bots, voice AI, IoT, ad
transparency); **consumer financial welfare** (mundane structural/format features producing large
welfare outcomes without consumer awareness — loan formats, joint accounts, payment frequency,
gift vs personal budgets); **health/medical decision-making** (a dedicated focus — Huang 2023 "5S"
curation); **sustainability** (food waste, green consumption, repair, packaging); **DEI / structural
inequality / non-WEIRD** populations as primary, not robustness checks.

## 13. The self-check before submission (run every box)

- [ ] Can you state the contribution as **"the field assumes X; we show not-X under C, because M"**?
- [ ] Is there a **named mechanism (M)**, and is it evidenced beyond a single measured mediation
      (manipulation-of-mediator or causal chain)?
- [ ] Is the surprise **real** (a believed assumption is overturned), not manufactured/HARKed?
- [ ] At least one **consequential behavioral DV**? Any **field/archival** anchor?
- [ ] **Boundary conditions** stated (the When/Where/Who)?
- [ ] Rivals **ruled out in dedicated studies**?
- [ ] **Pre-registered / open data**?
- [ ] Positioned as **reconciliation or problematization**, not a gap?
- [ ] **Timeliness** in the first paragraph; relevance woven throughout?
- [ ] If CCT/conceptual: a **named process model / reordering lens**, not a description/review?
