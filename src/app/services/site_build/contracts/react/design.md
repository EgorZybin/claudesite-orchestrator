# Design system — tokens and patterns for the React stack

This file gives you the TECHNICAL primitives — Tailwind tokens, CSS-variable
conventions, layout patterns, mobile breakpoints — needed to execute a
production-grade UI.

**This is NOT a recipe of defaults to copy.** Pick your aesthetic direction
per `frontend-design.md` (bold, distinct, not-AI-generic), then USE the
tokens here to express it. The Industry tone matrix below is INSPIRATION;
treat it as a starting hint, not a mandate. One well-executed unexpected
choice beats a textbook "conservative-legal default".

---

## Palette — HSL CSS variables (in src/theme.css)

All colors as HSL components (3-number form: `353 48% 32%`). The Tailwind
config wraps them in `hsl(var(--x))` automatically, so you reference them
as `bg-primary`, `text-foreground`, `border-border`, etc.

```css
@layer base {
  :root {
    --background: 38 28% 97%;        /* page bg */
    --foreground: 218 38% 12%;       /* main text */
    --card: 0 0% 100%;
    --card-foreground: 218 38% 12%;
    --primary: 353 48% 32%;          /* dominant — CTAs, key UI */
    --primary-foreground: 38 28% 97%;
    --secondary: 38 22% 92%;
    --secondary-foreground: 218 38% 18%;
    --accent: 25 80% 55%;            /* sharp pop — use sparingly */
    --accent-foreground: 0 0% 100%;
    --muted: 38 16% 88%;
    --muted-foreground: 218 14% 40%;
    --destructive: 0 70% 45%;
    --destructive-foreground: 0 0% 100%;
    --border: 38 18% 84%;
    --input: 38 18% 84%;
    --ring: 353 48% 32%;             /* focus ring */
    --radius: 0.5rem;
  }
}
```

### Palette commitment, not timidity

Per `frontend-design.md`: dominant colors with sharp accents outperform
timid, evenly-distributed palettes. Pick ONE dominant non-neutral hue
(`--primary`) and let it carry. Keep `--accent` rare — for moments of
emphasis, not as a second dominant. Avoid 5+ random-feeling colors.

Examples of strong palettes (DO NOT just copy):
- Editorial-luxury: warm cream `38 28% 97%` bg + wine `353 48% 32%` primary
  + brass `38 50% 50%` accent, near-black `218 38% 12%` text
- Warm hospitality: sage `120 15% 92%` bg + terracotta `15 60% 50%` primary
  + sand `40 45% 75%` muted, espresso `15 25% 18%` text
- Bold-tech: white `0 0% 100%` bg + electric indigo `260 90% 55%` primary
  + neon-cyan `180 100% 50%` accent, near-black text
- Brutalist: pure white + pure black + ONE saturated accent (red 0 80% 50%
  or yellow 50 100% 50%); no greys, sharp edges only

### Dark mode (optional, only if brief asks)

If a dark theme variant is needed, add `:root.dark { ... }` overrides for
each variable. Don't ship a dark theme by default — that's scope creep.

---

## Typography — display + body + mark

CSS variables hold the font family stacks. The Tailwind config maps them:
- `font-display` → `var(--font-display)` — headlines (h1-h4, hero, large
  callouts)
- `font-body` → `var(--font-body)` — paragraphs, lists, captions
- `font-mark` → `var(--font-mark)` — UI marks: badges, buttons, micro-labels

### Pairing rules (per frontend-design.md)

**NEVER**: Inter, Roboto, Arial, system-ui as `--font-display`. These are
the AI-generated default — instant tell.

**ALWAYS pair**: a distinctive display face with a comfortable body face.
Don't use the same family for both unless that's a deliberate aesthetic
(e.g. all-Cormorant for editorial-luxury).

### Pairing examples (DO NOT just copy)

| Tone | display | body | mark |
|---|---|---|---|
| Editorial-luxury | Cormorant Garamond | Source Serif 4 | IBM Plex Sans Condensed |
| Warm hospitality | Recoleta | Inter | Inter |
| Bold tech | Geist (or GT Sectra) | Geist | JetBrains Mono |
| Brutalist | Space Grotesk Bold | Plex Mono | Plex Mono |
| Editorial-magazine | Playfair Display | EB Garamond | Inter |
| Premium SaaS | Söhne (or PT Root UI) | Söhne | Söhne |
| Hand-crafted | DM Serif Display | Lora | DM Sans |

Fonts must be available as **Google Fonts** — the renderer doesn't host
custom font files. Add `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=...">`
in `Layout.tsx` or via the index.html template's `<!--app-head-->` marker.

For Söhne/Geist or any non-Google fonts, fall back to a Google equivalent.

### Type scale

Use Tailwind's default scale + careful sizing for display:

- h1: `text-4xl md:text-5xl lg:text-6xl` (with `font-display`,
  `tracking-tight` for sans, `text-balance` always)
- h2: `text-3xl md:text-4xl`
- h3: `text-2xl md:text-3xl`
- h4: `text-xl`
- body: `text-base` (16px) or `text-lg` (18px) for editorial sites
- mark: `text-xs uppercase tracking-wider` for badges/eyebrows

Line height: `leading-tight` for displays, `leading-relaxed` for body
prose. Long-form articles use `prose` patterns (max-width: 65ch, generous
paragraph spacing).

---

## Spacing & container

Tailwind defaults rule. Use the spacing scale (1/2/3/4/6/8/12/16/20/24/...).
Don't write arbitrary spacing like `mt-[17px]` unless it's a deliberate
nudge for a specific composition reason.

Container width is set in tailwind.config.ts: max-width `1180px` at the
`2xl` breakpoint. Use `container mx-auto px-6` for the standard wrapping.

---

## Hero patterns — pick per page_type AND per brief tone

Don't use the same hero composition on every page. Each page_type does a
different job:

### `home` — the sales pitch

Three composition options to choose from:

1. **Split** — h1 + sub + CTAs on the LEFT half, brand visual (illustration,
   pattern, photo collage, or hero_image cropped to a non-rectangular
   shape) on the RIGHT. Desktop only — mobile stacks.
2. **Centered-bold** — one giant h1 (`text-6xl lg:text-7xl`), short sub
   below, single CTA. Generous vertical breathing room. Works for
   luxury/editorial/premium.
3. **Full-bleed-bg** — `page.hero_image` as `background-image` on the hero
   block with a gradient overlay (`bg-gradient-to-b from-black/30 to-black/60`);
   text + CTA centered on top. Works for hospitality / food / lifestyle.
4. **Top-bar-hero** — thin trust-bar with metrics (`20+ лет · 10K+ дел ·
   4.9 рейтинг`) above an h1+sub+CTA. Works for conservative service
   industries.

### `service` — the offer

Breadcrumb above the h1 (`Услуги → Семейные споры`). Tight focus, one CTA.
Below the CTA, an anchor-list to in-page sub-sections (pricing, process, faq).

### `services` (overview) — the menu

Minimal hero: h1 + one-line sub, NO CTA in hero (the page IS the catalog).
Cards grid starts immediately below.

### `about` — the story

Narrative hero. Photo of founder/team OR a soft pattern, with the h1 to
the side. Make the h1 a STATEMENT not a label: "Мы строим, потому что
верим, что дом — это покой" beats "О нас".

### `blog_post` — the article

Minimal type-led: eyebrow (category + date), large h1, single-line sub,
optional `hero_image` full-bleed below the intro paragraph (NOT in the
hero block). No CTA in hero — the article IS the CTA. Article body
max-width: `max-w-prose` (about 65ch).

### `blog_index` — the library

Tiny hero (h1 + one sub line). Filter chips by tag (if categories exist in
content). Card grid for posts starting at `mt-8`, not `mt-20`. Density
beats hero presence.

### `contacts` — the open door

Two-column hero on desktop: form on the LEFT, `contact_info` block on the
RIGHT (address, phone, hours, embed-friendly map placeholder, social).
Mobile stacks. Form gets priority — visible above fold.

---

## Mobile responsiveness — non-negotiable

Tailwind breakpoints:
- `sm` 640px
- `md` 768px
- `lg` 1024px
- `xl` 1280px
- `2xl` 1536px

### Required behaviors

1. **Header `cta` button** must not overflow viewport at 360-480px.
   At `<sm` (i.e. mobile), hide the desktop CTA — put it inside a burger
   drawer (use the `Sheet` primitive from shadcn or roll your own with
   Radix Dialog).
2. **Nav** with >4 items should collapse into burger at `<lg` (1024px).
   Don't try to fit 6 nav links + brand + CTA on tablets.
3. **Cards grids** — `grid-cols-3 md:grid-cols-2 sm:grid-cols-1` is the
   standard down-step pattern.
4. **Hero h1** — `text-3xl sm:text-4xl md:text-5xl lg:text-6xl`. Don't
   leave a 56px headline on a 360px phone.
5. **Container padding** — `px-4 sm:px-6 lg:px-8` minimum (or use
   `container` shorthand which has center+padding built in).

Test mentally at 360px and 768px before declaring done.

---

## shadcn primitive usage — when to use which

You have three pre-shipped primitives. Don't re-implement these from scratch.

### Button

```tsx
import { Button } from "@/components/ui/button";

<Button>Primary CTA</Button>                              {/* default */}
<Button variant="secondary">Secondary</Button>
<Button variant="outline">Outline</Button>
<Button variant="ghost">Ghost — nav-link style</Button>
<Button variant="link">Inline link</Button>
<Button size="lg">Hero CTA</Button>
<Button size="sm">Compact</Button>
<Button asChild><a href="/contacts">Wrap an anchor</a></Button>
```

Use `default` for primary CTAs, `secondary` for the "second" action,
`ghost` inside the header for nav-style buttons, `link` for inline.

### Card

```tsx
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter }
  from "@/components/ui/card";

<Card>
  <CardHeader>
    <CardTitle>Service name</CardTitle>
    <CardDescription>One-line subtitle</CardDescription>
  </CardHeader>
  <CardContent>Body</CardContent>
  <CardFooter><Button>Подробнее</Button></CardFooter>
</Card>
```

Use for: service cards on services page, blog post cards on blog_index,
pricing plans, team members. NOT for hero. NOT for full-width sections.

### Accordion

```tsx
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent }
  from "@/components/ui/accordion";

<Accordion type="single" collapsible>
  {items.map((it, i) => (
    <AccordionItem key={i} value={`item-${i}`}>
      <AccordionTrigger>{it.question}</AccordionTrigger>
      <AccordionContent>{it.answer}</AccordionContent>
    </AccordionItem>
  ))}
</Accordion>
```

Use for FAQ sections (`modules.faq.items`). Don't use it for navigation
or content-organization — it implies "answer to a question".

### Need more primitives?

If you need Sheet (drawer), Tabs, Dialog, Input, Label, Separator, Badge,
etc. — write them as new files in `src/components/ui/`. The radix
deps for these are NOT in `package.json` — DON'T add them. Either:
- Use existing Tailwind+HTML to roll your own (simpler shadcn-style)
- Or compose from `@radix-ui/react-slot` (which IS available)

Examples: Badge is just a `<span>` with CVA-styled variants. Separator is
just a `<hr>`. Dialog is harder — for mobile drawer, you can build a basic
overlay+slide-in using `useState` + Tailwind transitions, without Radix.

---

## Industry tone matrix — INSPIRATION, not mandate

| Industry | Suggested tone | NOT a rule |
|---|---|---|
| legal, finance, medical | conservative-professional | but bold editorial CAN work |
| restaurant, hotel, wedding | warm hospitality | photo-heavy, large imagery |
| SaaS, devtools, b2b-tech | bold tech | bright accent, geometric sans |
| portfolio, agency, gallery | editorial-creative | asymmetric, large type |
| luxury, jewelry, real-estate | premium-luxury | deep neutrals + gold accent |
| nonprofit, education | warm-trustworthy | photography-led, optimistic |
| ecommerce, dtc | playful-energetic | OR refined-minimal, depends |

Treat these as the safe starting line, not the answer. Per frontend-design
skill, ONE unexpected choice (Cormorant for SaaS, brutalist for legal,
maximalist for finance) can completely separate the site from "AI-generated".

---

## Self-check before declaring done

1. Does App.tsx exist and dispatch by page_type?
2. Does src/theme.css exist with non-default CSS variables?
3. Does each page_type the site uses have its own component?
4. Does the header have a burger menu for `<lg` viewports?
5. Is `page.hero_image` guarded with `&&` everywhere it's used?
6. Is the font-display NOT Inter/Roboto/Arial?
7. Does the palette feel committed (one dominant, sharp accent) or timid?
8. Does mobile (360px) not overflow horizontally?
9. Does `vite build` complete without errors? (run mentally before declaring done)
