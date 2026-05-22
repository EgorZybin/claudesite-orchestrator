# Section examples — visual quality reference

These files are NOT for direct import. They demonstrate **distinctive, executable
section patterns** you should study before writing your own `src/components/sections/*`.
The goal: see what "production-grade" looks like for shadcn-stack landings, then
ADAPT (don't copy verbatim) to your brief's tone.

Each example is one section component using the immutable seed primitives
(`Button`, `Card`, `Accordion`) + Tailwind tokens + CSS variables. They show
concrete *pattern* choices: asymmetric grids, off-axis crops, type contrast,
intentional negative space, micro-trust strips.

| File | Pattern | When to use |
|---|---|---|
| `hero-split-editorial.tsx` | 60/40 split, serif h1, rotated photo card + decorative offset block, micro-stats strip | Editorial / luxury / professional-services (legal, consulting). Pairs with serif `--font-display`. |
| `hero-photo-overlay-bold.tsx` | Full-bleed `<picture>` with gradient overlay; oversized text bottom-left; minimal CTA | Hospitality, food, lifestyle, real-estate. Pairs with photo-rich content. |
| `feature-bento-asymmetric.tsx` | 6-item bento grid (2x3 desktop, 1 tall + 5 normal); each tile semantic-colored | SaaS, fintech, healthcare — when "features" module has 4-6 items + you want to break uniformity. |
| `pricing-emphasized-middle.tsx` | 3 plans, middle one floats above with `-translate-y-4` + ring; type-led contrast | Any site with `pricing` module + a recommended plan. |
| `footer-multicol-dense.tsx` | 5-col dense grid: brand+manifesto (2 col span) + 3 link columns + bottom legal bar; uses inverse colors | Default site footer when `footer` module + `contact_info` available. |

## How to read these

1. Open the file you want to mimic.
2. Read the **comment header** — explains WHY each design choice was made.
3. Note the Tailwind class patterns (not the values). Adapt classes to YOUR
   palette + spacing.
4. Reuse the STRUCTURE (grid layout, type hierarchy, decorative elements),
   not the literal copy.
5. NEVER import from `contracts/examples/` — these files are not in your build
   path. Write parallel `src/components/sections/<YourSection>.tsx`.

## What makes these "good" (vs. generic AI output)

- **Asymmetry**: 60/40 splits, off-axis rotations, breaking the 4-column grid.
- **Type contrast**: display serif paired with condensed sans (`font-mark`), tracking
  variations (`tracking-[0.18em]` on micro-labels).
- **Intentional negative space**: `py-24 lg:py-32`, generous margin-bottom.
- **Decorative elements**: rotation, gradient overlays, semantic-color tiles,
  hairline borders — not generic `border-gray-200`.
- **Micro-detail strips**: stats trio, eyebrow tags, "ago" markers — signal of
  thoughtful design.
- **Mobile collapse**: each grid stacks predictably on `< lg` (1024px).

Generic AI output usually defaults to: centered text, uniform grids, no
decorative tension, identical spacing across sections. Avoid that.
