# Build contract — React + Vite + Tailwind + shadcn stack

You are inside a per-site project workspace. Read this file in full BEFORE
writing any TSX. Then read `design.md` (Tailwind tokens, layout patterns),
`frontend-design.md` (aesthetic philosophy — bold, anti-generic), and
`examples/` (production-grade section exemplars — visual quality reference;
study but adapt, never import).

Your job: turn `brief.md` into a working React app that the renderer
service will SSR per request, with content streaming in from a Postgres-
backed DB.

If `brief.md` contains a **MANDATORY design tokens** section, the HSL
values and font families there OVERRIDE design.md and frontend-design.md
when they conflict. They were extracted from a reference site the user
explicitly wants matched.

---

## File layout — what's already here, what you write

The workspace was seeded with the files below. Read them with the Read tool
before writing anything that imports from them.

### IMMUTABLE — do not modify

These files are part of the build infrastructure or the type contract with
the orchestrator. Touching them breaks the pipeline.

```
package.json           — npm deps (don't add new ones; the renderer container
                         has them pre-installed against this exact list)
vite.config.ts         — two-pass build (client + ssr)
tailwind.config.ts     — theme tokens via hsl(var(--x)) indirection
postcss.config.js
tsconfig.json
index.html             — SSR template with <!--app-html-->, <!--app-title-->,
                         <!--app-description-->, <!--app-canonical-->,
                         <!--app-lang-->, <!--app-head--> markers (the
                         renderer splices values; don't change marker syntax)
src/main.tsx           — client hydration entry
src/entry-server.tsx   — SSR entry — exports render(props) -> { html, head }
src/index.css          — only @tailwind directives + a comment marker
src/types.ts           — TS contract for RenderProps; mirrors Pydantic types
                         on the Python side. Add fields here ONLY if you also
                         add them in the orchestrator (out of scope for a
                         normal site build).
src/lib/utils.ts       — cn() helper
src/lib/markdown.ts    — renderMarkdownInline(text) — for paragraph.markdown
src/components/ui/button.tsx     — shadcn Button (variant: default | destructive
                                   | outline | secondary | ghost | link)
src/components/ui/card.tsx       — shadcn Card, CardHeader, CardTitle,
                                   CardDescription, CardContent, CardFooter
src/components/ui/accordion.tsx  — shadcn Accordion (use for FAQ)
```

### REQUIRED — you must create these (or the build fails)

```
src/App.tsx     — root component, dispatches by page.page_type. See "App.tsx
                  contract" below.
src/theme.css   — CSS variables (palette, fonts, radius). Imported by
                  src/index.css. See "theme.css contract" below.
```

If either file is missing, `vite build` errors out and the site does not
publish.

### EXPECTED — you'll typically create most of these

Concrete file names are your call; what matters is that App.tsx renders
the right composition per page_type and the visual quality bar is hit.

```
src/components/Layout.tsx      — header + main + footer wrapper
src/components/Header.tsx      — sticky/static nav, brand mark, primary CTA
src/components/Footer.tsx      — multi-column footer with contact_info, links
src/pages/HomePage.tsx         — composes hero + featured modules + CTA
src/pages/ServicesPage.tsx     — services overview, iterates pages_in_site
                                 where page_type === "service"
src/pages/ServicePage.tsx      — single service detail
src/pages/BlogIndexPage.tsx    — blog cards, iterates pages_in_site where
                                 page_type === "blog_post"
src/pages/BlogPostPage.tsx     — article body, faq if present
src/pages/AboutPage.tsx        — narrative composition
src/pages/ContactsPage.tsx     — contact info, optional form placeholder
src/components/sections/*.tsx  — bespoke section components you compose
                                 from shadcn primitives
```

Not all of these are mandatory — only the page_types your site actually has
(see `brief.md` for the list). But each page_type that exists in the
`pages_in_site` array MUST have a renderer in App.tsx, or that page returns
the "unknown page_type" fallback at runtime.

---

## App.tsx contract

The root component takes `RenderProps` (see `src/types.ts`) and dispatches
on `page.page_type`. Wrap every branch in a single `<Layout>` so header/
footer stay consistent. Minimum viable:

```tsx
import type { RenderProps } from "./types";
import { Layout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
// ... other page imports

export function App(props: RenderProps) {
  return (
    <Layout {...props}>
      {renderPage(props)}
    </Layout>
  );
}

function renderPage(props: RenderProps) {
  switch (props.page.page_type) {
    case "home":      return <HomePage {...props} />;
    case "services":  return <ServicesPage {...props} />;
    case "service":   return <ServicePage {...props} />;
    case "blog_index":return <BlogIndexPage {...props} />;
    case "blog_post": return <BlogPostPage {...props} />;
    case "about":     return <AboutPage {...props} />;
    case "contacts":  return <ContactsPage {...props} />;
    default:
      return (
        <main className="container py-12">
          <h1>{props.page.title}</h1>
          <pre>unknown page_type: {props.page.page_type}</pre>
        </main>
      );
  }
}
```

You may extend this — add custom pages, conditional sub-routes, etc. — but
keep the dispatch by `page.page_type` as the entry pattern.

---

## theme.css contract

The Tailwind config references CSS variables that MUST exist at runtime:

```css
/* src/theme.css — written by Claude per brief.
   Import this from src/index.css via @import "./theme.css";  */
@layer base {
  :root {
    /* All colors as HSL components (no #hex, no rgb()) so accent shifts
       and dark-mode flips are trivial. */
    --background: 38 28% 97%;        /* page background */
    --foreground: 218 38% 12%;       /* main text on background */

    --card: 0 0% 100%;
    --card-foreground: 218 38% 12%;

    --primary: 353 48% 32%;          /* dominant brand color (CTAs, key UI) */
    --primary-foreground: 38 28% 97%;/* text on primary */

    --secondary: 38 22% 92%;
    --secondary-foreground: 218 38% 18%;

    --accent: 25 80% 55%;            /* sharp accent (sparingly) */
    --accent-foreground: 0 0% 100%;

    --muted: 38 16% 88%;
    --muted-foreground: 218 14% 40%;

    --destructive: 0 70% 45%;
    --destructive-foreground: 0 0% 100%;

    --border: 38 18% 84%;
    --input: 38 18% 84%;
    --ring: 353 48% 32%;             /* focus ring — usually same as primary */

    --radius: 0.5rem;

    --font-display: "Cormorant Garamond", "EB Garamond", Georgia, serif;
    --font-body: "Source Serif 4", Charter, Georgia, serif;
    --font-mark: "IBM Plex Sans Condensed", "Helvetica Neue", sans-serif;
  }
}
```

The values above are an EXAMPLE — pick palette + fonts per the brief's
tone (see `frontend-design.md`). All of these variables MUST be defined or
Tailwind utilities resolve to empty strings and the site looks broken.

After writing src/theme.css, add `@import "./theme.css";` to src/index.css.

---

## RenderProps — what the renderer passes to App()

Full type in `src/types.ts`. Key shape:

```ts
interface RenderProps {
  site: { brand, language, industry, tagline }
  page: {
    slug, page_type, title, seo_description,
    hero_title, hero_subtitle, hero_image,
    content_blocks: ContentBlock[],
    modules_used: string[],
  }
  modules: Record<string, ModuleData | null>  // ONLY modules listed in
                                              // page.modules_used are non-null
  nav: { label, href, current }[]              // up to 6 items
  current_url: string                          // for canonical / og:url
  pages_in_site: PageSummary[]                 // ALL published pages, for
                                              // index pages (blog/services)
}
```

### Available content_blocks (discriminated by `kind`)

```ts
{ kind: "heading", level: 2|3|4, text: string }
{ kind: "paragraph", markdown: string }    // pipe through renderMarkdownInline
{ kind: "image", src, alt, caption?, width?, height? }
{ kind: "list", ordered: boolean, items: string[] }
{ kind: "quote", text, attribution? }
{ kind: "table", headers, rows }
{ kind: "cta", label, href, style: "primary"|"secondary"|"ghost" }
```

Render `content_blocks` on detail pages (blog_post, service, about) via a
generic loop. On overview pages (home, services, blog_index, contacts)
use module data + bespoke sections instead — content_blocks on these
pages are typically intro paragraphs only.

### Available modules (only the ones in `page.modules_used` are non-null)

- `features` — `{ title?, items: [{ title, description, icon? }] }`
- `stats` — `{ items: [{ value, label }] }`
- `testimonials` — `{ title?, items: [{ quote, author, role?, photo? }] }`
- `pricing` — `{ plans: [{ name, price, period?, features, cta_label,
  cta_href, highlighted: boolean }] }` — EXACTLY one plan has highlighted=true
- `team` — `{ members: [{ name, role, bio?, photo? }] }`
- `faq` — `{ items: [{ question, answer }] }` — render via shadcn Accordion
- `contact_info` — `{ email?, phone?, address?, hours?, social? }`
- `footer` — `{ tagline?, columns: [{ title, links }], legal? }`

The `icon` field in features may be a single emoji or a lucide-react icon
name. Import from `lucide-react` and render inline; the renderer image bundles
lucide already, no extra setup.

---

## hero_image — handle it correctly

`page.hero_image` is `string | null`. By render time it MAY be set even if
the brief snapshot shows null (image generation runs in parallel with the
build). ALWAYS guard:

```tsx
{page.hero_image && (
  <picture>
    <source type="image/avif"
            srcSet={`${page.hero_image.replace('.webp', '.avif').replace('-1280', '-640')} 640w,
                     ${page.hero_image.replace('.webp', '.avif').replace('-1280', '-960')} 960w,
                     ${page.hero_image.replace('.webp', '.avif')} 1280w`}
            sizes="(max-width: 720px) 100vw, 720px" />
    <source type="image/webp"
            srcSet={`${page.hero_image.replace('-1280', '-640')} 640w,
                     ${page.hero_image.replace('-1280', '-960')} 960w,
                     ${page.hero_image} 1280w`}
            sizes="(max-width: 720px) 100vw, 720px" />
    <img src={page.hero_image}
         alt={page.hero_title || page.title}
         loading="eager"
         decoding="async" />
  </picture>
)}
```

NEVER hardcode an `/uploads/...` path — always read from `page.hero_image`.

Whether to USE the image is a per-page-type call (see `design.md`):
- home, blog_post, about — typically yes
- service, blog_index, contacts — context-dependent

If you decide not to use the image on a particular page_type, that's fine
— but the conditional guard is non-negotiable.

---

## Validation — what the build pipeline checks

After `vite build` completes, the orchestrator's validator verifies:

1. `dist/server/entry-server.js` exists (App.tsx was written + compiled)
2. `dist/client/index.html` exists (template ready for SSR)
3. `dist/client/.vite/manifest.json` exists (asset paths discoverable)
4. `dist/client/assets/*.css` exists with at least one rule containing
   `hsl(` (proves theme.css was authored — not the default unstyled state)

If any check fails, the build does NOT publish. Vite's error log goes back
to the orchestrator, which surfaces it in the job's error field.

---

## Anti-patterns — things that will be rejected

- ❌ **Inter or Roboto or Arial as --font-display** — see frontend-design.md
- ❌ **Purple gradients on white background** — generic AI look
- ❌ **Adding deps to package.json** — the renderer container has fixed deps
- ❌ **Editing files marked IMMUTABLE above**
- ❌ **Hardcoding `/uploads/` paths in img src** — use `page.hero_image`
- ❌ **8+ items in nav (page.modules_used or pages_in_site filter)** — the
  orchestrator caps at 6, your template should not assume more
- ❌ **Skipping the `{page.hero_image && (...)}` guard** — image may be null
- ❌ **`block.props.X` access** — content blocks expose fields DIRECTLY
  (block.markdown, block.text, block.level, etc.) per src/types.ts

---

## When you're done

Write a 2–3 sentence summary of: (a) the aesthetic direction you
committed to, (b) one concrete non-default choice you made (font family,
palette, layout pattern), (c) which page_types you implemented as
dedicated components vs left to the App.tsx default fallback.
