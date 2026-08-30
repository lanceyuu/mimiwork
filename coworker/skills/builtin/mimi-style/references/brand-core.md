# Brand core — copy-paste tokens

## CSS custom properties

```css
:root {
  --mimi-teal: #0D9488;
  --mimi-teal-dark: #0B7C72;
  --mimi-teal-mid: #8ED6CC;
  --mimi-tint: #E9F6F4;
  --mimi-tint-deep: #D9EFEC;
  --mimi-ink: #111111;
  --mimi-muted: #555555;
  --mimi-line: #E6E6E6;
  --mimi-paper: #FAFAFA;
  --mimi-font: "Avenir Next", "Nunito", "Helvetica Neue", Arial, sans-serif;
}
body { background: var(--mimi-paper); color: var(--mimi-ink); font-family: var(--mimi-font); }
a { color: var(--mimi-teal); }
```

## Python constants (matplotlib, PIL, python-pptx)

```python
TEAL, TEAL_DARK, TEAL_MID = "#0D9488", "#0B7C72", "#8ED6CC"
TINT, TINT_DEEP = "#E9F6F4", "#D9EFEC"
INK, MUTED, LINE, PAPER = "#111111", "#555555", "#E6E6E6", "#FAFAFA"
FONT = "Avenir Next"   # fall back to "Helvetica Neue" / Arial
CHART_SERIES = [TEAL, TEAL_MID, "#3B6B66", "#BFE3DE"]  # in this order
```

## Wordmark

There is no image wordmark in the asset pack. Set the product name in the brand font,
semibold, ink (or white on teal): "QualiTaTi" (capital Q, T, T) · "MimiWork" (capital M, W).
Never letterspace, never all-caps, never a gradient.

## Charts

Bars/lines in TEAL; second series TEAL_MID; never red/green together (the red reads as
the China set and as error). Grid hairlines LINE, labels MUTED, title INK left-aligned.
Spines off top/right. Numbers that matter get TEAL; everything else stays quiet.

## Do not

- No drop shadows heavier than `0 2px 8px rgba(0,0,0,.08)`; no gradients; no emojis.
- No red set outside the China site. No recolored icons — use the provided families.
- No pure-black (#000) text and no pure-white page edge: ink is #111, paper is #FAFAFA.
