/**
 * HERO PATTERN: Split editorial composition (text-left 60% / image-right 40%)
 *
 * WHEN TO USE:
 *   editorial, luxury, premium, conservative-professional — anywhere the
 *   brief calls for spacious, considered tone. Pairs naturally with serif
 *   `--font-display` (Cormorant Garamond, Source Serif 4, Playfair Display).
 *
 * PATTERN HIGHLIGHTS:
 *   1. 60/40 grid on `lg+`, stacks on `< lg`
 *   2. Oversized serif h1 with `tracking-tight` + `leading-[0.95]` +
 *      `text-balance` — type as the primary visual element
 *   3. Eyebrow (`font-mark` condensed sans + uppercase + wide tracking)
 *      gives type-pair contrast above h1
 *   4. Image card intentionally rotated -1.5deg + decorative card behind
 *      at +2deg — creates depth and "designed" feel without imagery
 *   5. Micro-trust strip below CTA (trio of stats with hairline dividers)
 *      breaks the "just a hero" pattern and earns trust at zero text cost
 *   6. Generous vertical breathing (`py-24 lg:py-32`)
 *
 * ANTI-PATTERNS THIS AVOIDS:
 *   ✗ centered text + image-below stack — that's the default everyone uses
 *   ✗ symmetric 50/50 split — feels mechanical
 *   ✗ photo without any frame/treatment — feels like clipart
 *   ✗ tiny h1 + huge subtitle — invert it; h1 IS the visual
 */
import { Button } from "@/components/ui/button";
import type { RenderProps } from "@/types";

export function HeroSplitEditorial(props: RenderProps) {
  const { page, site, modules } = props;
  const stats = (modules.stats as { items?: { value: string; label: string }[] } | null)?.items ?? [];

  return (
    <section className="relative overflow-hidden border-b border-border">
      <div className="container py-24 lg:py-32">
        <div className="grid lg:grid-cols-[1.2fr_1fr] gap-12 lg:gap-20 items-center">
          {/* LEFT: type block */}
          <div>
            <p className="font-mark text-xs tracking-[0.22em] uppercase text-muted-foreground mb-7">
              {page.hero_title ?? site.brand}
            </p>
            <h1 className="font-display text-5xl md:text-6xl lg:text-7xl font-medium tracking-tight leading-[0.95] text-balance mb-7">
              {page.title}
            </h1>
            {page.hero_subtitle && (
              <p className="text-lg md:text-xl text-muted-foreground max-w-xl mb-10 leading-relaxed">
                {page.hero_subtitle}
              </p>
            )}
            <div className="flex flex-wrap gap-3 mb-12">
              <Button size="lg" asChild>
                <a href="/contacts">Записаться на консультацию</a>
              </Button>
              <Button size="lg" variant="ghost" asChild>
                <a href="/services">Наши услуги →</a>
              </Button>
            </div>

            {/* Micro-trust strip */}
            {stats.slice(0, 3).length === 3 && (
              <div className="flex divide-x divide-border border-y border-border max-w-md">
                {stats.slice(0, 3).map((s, i) => (
                  <div key={i} className="flex-1 py-5 first:pr-6 last:pl-6 px-6">
                    <div className="font-display text-3xl md:text-4xl font-medium tracking-tight">
                      {s.value}
                    </div>
                    <div className="font-mark text-[10px] uppercase tracking-[0.18em] text-muted-foreground mt-1.5">
                      {s.label}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* RIGHT: image card with decorative offset */}
          {page.hero_image && (
            <div className="relative">
              <div className="aspect-[4/5] rounded-md overflow-hidden -rotate-[1.5deg] shadow-2xl ring-1 ring-border">
                <img
                  src={page.hero_image}
                  alt={page.hero_title ?? page.title}
                  className="w-full h-full object-cover"
                  loading="eager"
                  decoding="async"
                />
              </div>
              {/* Decorative card behind, rotated opposite way */}
              <div
                aria-hidden="true"
                className="absolute -inset-x-3 -inset-y-3 -z-10 aspect-[4/5] rounded-md bg-primary/8 rotate-[2deg]"
              />
              {/* Tag overlay top-right */}
              <div className="absolute top-4 right-4 bg-foreground text-background font-mark text-[10px] uppercase tracking-[0.2em] px-3 py-1.5">
                {site.industry || site.brand}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
