# Slot contract — what your templates receive

You (Claude) generate Jinja2 templates that the orchestrator renders with content
fetched from MySQL at request time. This document defines the **contract** between
your templates and the runtime content layer.

You MUST follow it exactly. Templates that ask for slots not listed here will
receive `None`/empty. Templates that don't use the slots a page_type declares
will fail manifest validation.

---

## Global context (available in EVERY template)

```jinja2
{{ site.brand }}           # str — brand name, e.g. "Cybersport"
{{ site.tagline }}         # str | None — 1-sentence pitch
{{ site.language }}        # str — ISO-639-1, e.g. "ru", "en"
{{ site.industry }}        # str — domain identifier, useful for conditional styling

{{ nav }}                  # list of {label, href, current}
                           #   label: str — short menu label
                           #   href:  str — "/" + page.slug
                           #   current: bool — True if it's THIS page

{{ footer }}               # FooterModule data:
                           #   tagline: str | None
                           #   columns: list[{title, links: list[{label, href}]}]
                           #   legal:   str — "© YYYY Brand"

{{ current_url }}          # str — full URL of THIS page, for canonical and OG tags
{{ assets }}               # str — base path for static assets, e.g. "/assets/{site_id}/v15"

{{ pages_in_site }}        # list[dict] — ALL published pages of this site (for
                           # index templates: blog_index lists blog_post pages,
                           # services overview lists service pages, home can show
                           # recent posts). Each entry:
                           #   slug:            str — page slug
                           #   title:           str — full SEO title
                           #   page_type:       str — home|services|service|blog_index|blog_post|about|contacts|...
                           #   href:            str — ready-to-use URL ("/about" on host-domain,
                           #                          "/public/<site>/about" on orchestrator-domain)
                           #   nav_label:       str | None — short label or null if not in nav
                           #   seo_description: str — for card descriptions
                           #   hero_title:      str | None — alt to title for card heading
                           #   hero_subtitle:   str | None — short pitch
                           #   hero_image:      str | None — path under /uploads/<site>/
                           #   sort_order:      int — deterministic ordering
```

Use `{{ assets }}/styles/bundle.{hash}.css` and `{{ assets }}/scripts/bundle.{hash}.js`
in your `<head>`. Hashes come from `manifest.asset_hashes`.

**`pages_in_site` is REQUIRED for index-type pages.** Index templates (blog_index,
services, possibly home with "recent posts") MUST iterate the relevant subset
of `pages_in_site` to render cards. Without this, child pages are unreachable
from navigation. Example:

```jinja2
{# blog_index.html — list all blog_post pages as cards #}
<section class="posts">
  {% for post in pages_in_site if post.page_type == 'blog_post' %}
    <article class="post-card">
      <a href="{{ post.href }}">
        <h3>{{ post.hero_title or post.title }}</h3>
        <p>{{ post.hero_subtitle or post.seo_description }}</p>
      </a>
    </article>
  {% endfor %}
</section>

{# services.html — list service-detail pages as cards #}
<section class="service-list">
  {% for s in pages_in_site if s.page_type == 'service' %}
    <a href="{{ s.href }}" class="service-card">
      <h3>{{ s.hero_title or s.title }}</h3>
      <p>{{ s.seo_description }}</p>
    </a>
  {% endfor %}
</section>
```

Do NOT iterate pages_in_site on detail pages (blog_post, service, about, contacts) —
those don't list children. Use it only on index/overview pages.

---

## Per-page context (available in page-type templates)

```jinja2
{{ page.title }}             # str — used as <title> and main H1
{{ page.seo_description }}   # str — for <meta name="description"> and OG
{{ page.hero_title }}        # str | None — short heading for hero slot
{{ page.hero_subtitle }}     # str | None — supporting line
{{ page.hero_image }}        # str | None — path to /uploads/...

{{ page.content_blocks }}    # list of semantic blocks — see Block render below

{{ modules }}                # dict — ONLY modules listed in page.modules_used are
                             # populated; others are `None`. Always check existence.
```

### Block render contract

Each item in `page.content_blocks` has a `kind` discriminator:

```jinja2
{% for block in page.content_blocks %}
  {% if block.kind == "heading" %}
    <h{{ block.level }}>{{ block.text }}</h{{ block.level }}>
  {% elif block.kind == "paragraph" %}
    <p>{{ block.markdown | markdown_inline }}</p>     # filter renders inline md
  {% elif block.kind == "image" %}
    <figure>
      <img src="{{ block.src }}" alt="{{ block.alt }}"
           {% if block.width %}width="{{ block.width }}"{% endif %}
           {% if block.height %}height="{{ block.height }}"{% endif %}
           loading="lazy" decoding="async">
      {% if block.caption %}<figcaption>{{ block.caption }}</figcaption>{% endif %}
    </figure>
  {% elif block.kind == "list" %}
    {% if block.ordered %}<ol>{% else %}<ul>{% endif %}
      {% for item in block.items %}<li>{{ item | markdown_inline }}</li>{% endfor %}
    {% if block.ordered %}</ol>{% else %}</ul>{% endif %}
  {% elif block.kind == "quote" %}
    <blockquote>
      <p>{{ block.text }}</p>
      {% if block.attribution %}<cite>{{ block.attribution }}</cite>{% endif %}
    </blockquote>
  {% elif block.kind == "table" %}
    <table>
      <thead><tr>{% for h in block.headers %}<th>{{ h }}</th>{% endfor %}</tr></thead>
      <tbody>{% for row in block.rows %}
        <tr>{% for cell in row %}<td>{{ cell }}</td>{% endfor %}</tr>
      {% endfor %}</tbody>
    </table>
  {% elif block.kind == "cta" %}
    <a href="{{ block.href }}" class="cta cta-{{ block.style }}">{{ block.label }}</a>
  {% endif %}
{% endfor %}
```

You can wrap blocks however you want (extra divs, sections, classes) — the contract
is on what's IN the block, not how you frame it.

---

## Module render contracts

Only render a module if `page.modules_used` contains its name. Use the
`{% if "<name>" in page.modules_used %}` guard or check `modules.<name>`.

### features
```python
modules.features = {
    "title": str | None,                  # optional section heading
    "items": [{"title": str, "description": str, "icon": str | None}]
}
```
`icon` may be a single emoji ("⚡") or a lucide-name token ("zap"). For lucide-names,
inline the SVG yourself — the runtime does NOT inject lucide icons.

### stats
```python
modules.stats = {"items": [{"value": str, "label": str}]}
```

### testimonials
```python
modules.testimonials = {
    "title": str | None,
    "items": [{"quote": str, "author": str, "role": str | None, "photo": str | None}]
}
```

### pricing
```python
modules.pricing = {
    "plans": [{"name": str, "price": str, "period": str | None,
               "features": [str], "cta_label": str, "cta_href": str,
               "highlighted": bool}]
}
```
Exactly one plan has `highlighted=True` — render it visually distinct.

### team
```python
modules.team = {"members": [{"name": str, "role": str,
                              "bio": str | None, "photo": str | None}]}
```

### faq
```python
modules.faq = {"items": [{"question": str, "answer": str}]}
```
Prefer `<details><summary>` for accordion-style FAQ.

### contact_info
```python
modules.contact_info = {
    "email": str | None, "phone": str | None, "address": str | None,
    "hours": [str] | None,                # ["Пн-Пт 10:00–19:00", "Сб 11:00–17:00"]
    "social": [{"channel": str, "href": str, "label": str}]
}
```

---

## Required output files

You MUST produce:

```
templates/
  _layout.html              # base shell: <html>, <head>, <body>, nav, footer
                            # uses {% block content %}{% endblock %} for page body
  _partials/
    nav.html                # nav rendered with `nav` global
    footer.html             # footer rendered with `footer` global
  home.html                 # extends _layout.html
  services.html             # ditto
  service.html              # ditto
  blog_index.html           # ditto
  blog_post.html            # ditto
  about.html                # ditto
  contacts.html             # ditto

styles/
  bundle.{hash}.css         # ALL styles, content-addressable hash in filename

scripts/
  bundle.{hash}.js          # interactivity ONLY: mobile nav toggle, accordion polish,
                            # form validation. Empty file is fine if no JS needed.

manifest.json               # see manifest schema below
```

## manifest.json schema

```json
{
  "schema_version": "1",
  "generator": "claude-cli",
  "generated_at": "<ISO timestamp>",

  "page_types": ["home", "services", "service", "blog_index",
                 "blog_post", "about", "contacts"],

  "page_slots": {
    "home":       ["hero", "content_blocks", "features", "stats",
                   "testimonials", "faq", "cta"],
    "service":    ["hero", "content_blocks", "features", "pricing", "faq", "cta"],
    "blog_post":  ["hero", "content_blocks", "faq", "cta"],
    "blog_index": ["hero", "posts_list", "cta"],
    "about":      ["hero", "content_blocks", "team", "stats", "cta"],
    "contacts":   ["hero", "contact_info"],
    "services":   ["hero", "content_blocks", "cta"]
  },

  "asset_hashes": {
    "css": "<first 8 chars of sha256(styles/bundle file content)>",
    "js":  "<first 8 chars of sha256(scripts/bundle file content)>"
  },

  "design_tokens": {
    "accent_hsl": "210 100% 50%",
    "neutral_family": "slate",
    "display_font": "Inter, system-ui, sans-serif",
    "body_font": "Inter, system-ui, sans-serif",
    "radius_base": 8,
    "spacing_unit": 4,
    "dark_mode": false
  },

  "supports": {
    "dark_mode": false,
    "rtl": false,
    "print_styles": false,
    "reduced_motion": true
  },

  "notes": "Optional notes to your future self for edit consistency."
}
```

**Critical:** `page_slots["<type>"]` must list ONLY slots the template ACTUALLY uses.
If your `home.html` doesn't render `modules.testimonials`, don't list "testimonials"
in `page_slots["home"]`. Orchestrator uses this list to decide which modules to
fetch from MySQL for that page.

---

## Hard rules

- **Use Jinja2 syntax** — `{{ }}`, `{% %}`, `{# #}`, filters with `|`.
- **`_layout.html` defines `{% block content %}{% endblock %}`**; every page extends
  it with `{% extends "_layout.html" %}{% block content %}...{% endblock %}`.
- **Include partials** with `{% include "_partials/nav.html" %}` — keep partials in
  `_partials/` only.
- **NEVER** import external CSS or JS at runtime (no `@import url(https://...)`,
  no `<script src="https://cdn..."`). Orchestrator self-hosts fonts.
- **NEVER** use Tailwind utility classes — there's no Tailwind in the runtime.
- **NEVER** use React, Vue, Alpine.js, or any framework. Vanilla JS only.
- **NEVER** write to files outside this workspace.
- **DO NOT** use Jinja extensions beyond the default + `autoescape` — orchestrator
  runs templates in `SandboxedEnvironment`.

## Available Jinja filters and functions

Beyond Jinja defaults (`|safe`, `|default`, `|length`, `|join`, `|upper`, `|lower`):

- `| markdown_inline` — render inline-md (bold, italic, link, code) — safe to use on
  `paragraph.markdown` and `list.items[i]`
- `| markdown_block` — render full markdown including paragraphs/lists/headings —
  AVOID in templates; content_blocks already provide semantic structure
- `| iso_date('en')` / `| iso_date('ru')` — format ISO timestamp human-readable
- `url_for(slug)` — get internal href to a page by slug
- `has_module(name)` — bool check, prefer over `modules.<name> is not none`
