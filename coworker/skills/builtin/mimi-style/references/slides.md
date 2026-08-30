# Slides

16:9 always. The deck argues a case: title slides state takeaways, not topics.

- Title slide: teal rule (4pt, ~1.6in) above the title, title 40pt semibold ink,
  subtitle 18pt muted. `mascot/puppy-sitting.png` bottom-right at ~1in, optional.
- Section slides: teal bar flush to the left edge, 34pt title.
- Content: 28pt slide titles with a short teal rule under; body 18pt, at most 6 bullets;
  prefer a statement / big-stat / comparison layout over a third consecutive bullet slide.
- Stat slides: the number in teal 66pt; label 14pt muted below a hairline.
- Icons: one `tiles/` icon top-right of a section, or `outline/` icons in comparison
  columns — one family per deck.
- Backgrounds: paper; one tint (`#E9F6F4`) band or card per slide at most. Dark closing
  slide allowed: teal background, white text, `dark/` icons only.
- Charts: per brand-core.md; place as full-width images with a one-line caption in muted.

In MimiWork, pass a branded template to `write_presentation` when one exists; otherwise
build slides as HTML (this system) and export.
