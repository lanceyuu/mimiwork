---
name: qualitati-style
description: MimiWork's default skill for creating or restyling slides and presentations. Tailor the deck to its audience and purpose with editorial serif typography, natural photography, editable evidence and speaker notes. Follow an explicit visual direction or house template.
---

# QualiTaTi presentation style

## Learn what this presentation has to do

Read the request, earlier answers and relevant supplied material first. Before drafting, fill the gaps that would change the deck. Use one grouped `ask_user` call with up to four short questions, concrete choices and free text. Ask in the user's language. If the tool is unavailable, ask in a single chat message and wait. A complete brief, a narrow revision, or a request to use your judgment can proceed directly.

Choose the questions that matter for this particular talk:

- Who will see it, what do they already know, and what should they understand, decide or do afterward?
- How will they use it? A ten-minute live pitch needs different pacing and notes from a leave-behind that people will read alone. Ask about duration or slide count when unknown.
- What story, evidence or examples must appear? Identify supplied notes, figures and required sources. For a revision, establish what must stay and what can change.
- Which constraints would affect delivery? Ask about a required template, language, tone, image library, accessibility needs or output format when relevant. Offer the editorial default when design is delegated.

Recommend choices specific to the topic. For a clinic pilot, for example, offer a funding decision brief, a staff training walkthrough or a patient introduction. Use the answer throughout the deck: a funding audience needs evidence and a decision, while staff need a realistic sequence and a chance to practice. State any material assumptions briefly and continue. Keep the source of facts and the source of photographs in the notes.

## Compose for this audience

Start with the actual question, finding or decision. Write the sequence of idea-led titles so that reading them in order tells the story. Give each slide one job. Keep essential definitions, figures, units, examples and qualifications visible. Use the notes for the presenter's explanation, source details, timings and discussion prompts. Use direct affirmative wording in the requested language and commas between inline labels. Label illustrative data where it appears.

Use a 16:9 canvas for a new deck unless the template or brief specifies otherwise. Set large, regular Instrument Serif titles and DM Sans body text, labels and notes where supported. Fonts and their open licenses are in `assets/fonts/`. Georgia and Arial are practical fallbacks for Latin text. For other scripts, use typefaces that support the language. The native PowerPoint writer uses Arial for portable body text by default. Include its font note when handing over the file.

Use warm paper (#FAFAF7), ink (#111C1B), muted text (#65706B) and teal (#0D9488). Use darker teal (#0B7C72) for small accent text and mint (#8ED6CC) against deep dark (#081513). Begin each title block with the title. Place timing or context below it. Separate elements with whitespace. Omit decorative rules, eyebrows, section numerals, card grids and isolated statistic tiles. Show quantities with their units and meaning. Use a shared baseline or an editable diagram when a relationship matters.

Choose the composition that explains the idea. A photograph can introduce a setting, an editorial split can pair a real scene with an insight, and a quiet evidence slide can let a figure carry the argument. Use distinct, relevant photographs from supplied or licensed sources. Inspect the crop and keep faces, hands and evidence visible. Record credits. If suitable photos are unavailable, choose a typographic slide, figure or diagram. Add product branding only when requested.

## Produce and check the deck

Use the requested destination. For PowerPoint use `write_presentation` with editable titles, text and notes. Use `photo_split` for photography beside an idea, adjust `photo_focus` to keep the subject visible, and use `image` to show a complete chart or screenshot with its labels. Follow explicit templates and visual references. For a new deck with a specified palette or typefaces, pass them in the writer’s `style` field. Vary layouts with the story.

For revisions, inventory the source deck first, including figures, embedded labels, timings, notes and credits. Keep meaningful figures visible on the slides and improve layout around them. A text-only readback cannot reconstruct a deck. Work on a new revision unless directed otherwise and use an editing path that preserves the source elements. Explain any material replacement or omission.

Reopen the result and verify titles, content, notes, assets and slide count. Resolve layout warnings. When rendering is available, inspect every slide and then the sequence for fit, crop, contrast and repetitive imagery. Check inherited title decorations as well. Distinguish the checks actually performed from destination rendering that remains unverified.
