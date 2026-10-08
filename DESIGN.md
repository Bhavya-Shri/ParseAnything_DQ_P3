# ParseAnything design system

> Adapted from the [Glyphs](https://glyphsapp.com) specimen captured by Inspo. The source is a type tool: large roman headlines, wide margins, one accent. The neon lime from that page is not used. This product is a reading instrument, so the accent stays dull and the paper stays warm.

- **Source:** https://glyphsapp.com
- **Adapted:** 2026-10-08
- **Mode:** light
- **Macrostructure:** Type specimen

## Tone

A document is set like a proof. Headlines are large and roman, body text sits in a narrow measure, and chrome stays out of the way. One deep olive is used for the active state and the primary action. Risk is named in words, not painted in traffic-light color.

## Colors

| Hex | Role |
|---|---|
| `#f3f0ea` | page |
| `#1c2416` | ink, primary button |
| `#5c6558` | muted text |
| `#d9d4cb` | hairline |
| `#3f4f34` | accent, used sparingly |
| `#6b3a2a` | critical text only |

Color words: *warm paper*, *ink*, *olive*

## Typography

| Role | Family | Size | Weight | Line-height | Letter-spacing |
|---|---|---|---|---|---|
| h1 | Newsreader | 4.6rem | 400 | 0.96 | 0 |
| h2 | Newsreader | 1.7rem | 400 | 1.2 | 0 |
| body | Newsreader | 1.2rem | 400 | 1.45 | 0 |
| ui | Hanken Grotesk | 0.92rem | 400 | 1.35 | 0 |
| caption | Hanken Grotesk | 0.75rem | 500 | 1.3 | 0.08em |

UI captions are set in small caps. The document itself is not.

## Spacing scale

`8px` · `16px` · `40px` · `80px`

## Border radius

`0` on panels and buttons. `2px` on the file control only.

## Container

Max content width: **1120px**

## CSS variables

```css
:root {
  --page: #f3f0ea;
  --ink: #1c2416;
  --muted: #5c6558;
  --line: #d9d4cb;
  --accent: #3f4f34;
  --critical: #6b3a2a;
  --paper: #f7f5f1;
  --serif: "Newsreader", "Iowan Old Style", "Palatino Linotype", Palatino, serif;
  --sans: "Hanken Grotesk", "Avenir Next", "Segoe UI", sans-serif;
  --measure: 38rem;
  --header: 4.25rem;
}
```

## Components

- Masthead with the parsed title
- Document proof, in reading order
- Evidence graph, on its own tab
