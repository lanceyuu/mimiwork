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

## Choose and source the visual

Choose the visual that answers the audience's question. A photograph can establish a place or show an object in use. A diagram can explain how parts interact. A chart can show measured differences. Preserve useful supplied assets and follow any restrictions in the brief.

**Search first.** Once the brief is sufficient, plan the job of each visual. For any real subject that needs a photograph, use `search_slide_photos` before calling `generate_image`. Search for what should actually be visible (for example, “residential heat pump outdoor unit”). Compare candidates by subject, composition, dimensions and rights. Call `save_slide_photo` with the chosen ID and its original extension, then inspect the actual image. A photo and a mechanism illustration serve different jobs: complete photo sourcing first when both are needed. Use supplied visuals first when they meet the brief.

**Real subjects.** If the dedicated search returns no suitable photo, try a simpler query, then use `web_search` to look in a different open collection. Search for the actual subject, action and setting, with terms such as “CC0” or “public domain”. Good starting points include Smithsonian Open Access and Wikimedia Commons. Use `web_fetch` to open the original item or file page and check the rights statement for that specific image. For an “IP-free” request, select images explicitly marked public domain or CC0. Use other licenses only when the brief permits their terms. Follow any required attribution placement. Skip candidates with unclear rights or distracting branding.

Download the selected original or a suitable high-resolution version into the task folder using an available download method. Use `read_image_info` to check its dimensions. For a full-width photograph on a 1920-pixel slide, aim for at least 1920 usable pixels across after cropping. Review the final crop for sharpness, a clear subject, natural lighting and room for the title. Select distinct images for different ideas. Keep the creator, source page, rights designation and license link in the slide notes. The item-specific Commons rights metadata returned by the photo tool is acceptable evidence even if the HTML page is blocked. If no verifiable photo fits after trying another source, use a deliberate typographic layout and disclose the missing photograph. Never present generated scenery as a documentary photograph.

**Complex concepts.** When the audience needs to see a mechanism, an invisible process or a spatial relationship, use `generate_image` for a purpose-built illustration. For example, to show how a heat pump transfers energy, describe the indoor and outdoor sides, where heat enters and leaves, and which components the viewer needs to distinguish. Specify the viewing angle, reading direction and final slide frame. Request a landscape illustration for a wide figure. Keep the title, precise labels, arrows and numerical data in editable slide elements where supported. Use supplied evidence for factual charts.

Use GPT Image 2.5 through the existing QualiTaTi image tool where the account's image route supports it. The gateway selects the provider for the active region and tier. Keep that route and its normal approval and credit handling. Save the returned image in the task folder, check the depicted relationships against the source, and place it on the slide with `image` or `photo_split`. Credit it as an AI-generated illustration in the notes. Name a specific model only when confirmed. If generation is unavailable or declined, explain the idea with a source figure or an editable diagram.

## Produce and check the deck

Use the requested destination. For PowerPoint use `write_presentation` with editable titles, text and notes. Use `photo_split` for photography beside an idea, adjust `photo_focus` to keep the subject visible, and use `image` to show a complete chart or screenshot with its labels. Follow explicit templates and visual references. For a new deck with a specified palette or typefaces, pass them in the writer’s `style` field. Vary layouts with the story. Let a documentary photo introduce the real setting, give the key mechanism room on its own slide, and use a quieter text slide when the takeaway needs no illustration. Keep text off busy images.

For revisions, inventory the source deck first, including figures, embedded labels, timings, notes and credits. Keep meaningful figures visible on the slides and improve layout around them. A text-only readback cannot reconstruct a deck. Work on a new revision unless directed otherwise and use an editing path that preserves the source elements. Explain any material replacement or omission.

Reopen the result and verify titles, content, notes, assets and slide count. Resolve layout warnings. When rendering is available, inspect every slide and then the sequence for fit, crop, contrast and repetitive imagery. Check inherited title decorations as well. Distinguish the checks actually performed from destination rendering that remains unverified.
