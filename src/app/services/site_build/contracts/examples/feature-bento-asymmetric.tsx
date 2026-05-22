/**
 * FEATURE PATTERN: Asymmetric bento grid (6 items, mixed sizes)
 *
 * WHEN TO USE:
 *   SaaS, fintech, healthcare, dev-tools — any site whose `modules.features`
 *   has 4-6 items and the brief calls for modern / bold tone. Breaks the
 *   default 3-column uniform grid that screams "AI template".
 *
 * PATTERN HIGHLIGHTS:
 *   1. Grid `lg:grid-cols-3 lg:grid-rows-2` — 6 cells total
 *   2. First feature spans `col-span-2 row-span-2` — hero-sized, gets a
 *      decorative gradient background + larger icon + longer description
 *   3. Remaining 5 features fill smaller cells, each with its own muted
 *      semantic-color tint (`bg-muted`, `bg-secondary`, etc) — variety
 *      without screaming
 *   4. Hairline borders (`border border-border`) instead of shadows —
 *      editorial / refined feel; swap for `shadow-lg` if "playful" tone
 *   5. Section heading uses `font-display` + max-w-2xl + measured padding
 *      — let the section have its own header treatment, not generic
 *
 * GRACEFUL FALLBACKS:
 *   - <4 items: hides the section (returns null)
 *   - 4 items: dropping the 5th + 6th cells, grid auto-fills
 *   - >6 items: only first 6 used; if site needs more, write a different layout
 */
import type { RenderProps } from "@/types";

type FeatureItem = { title: string; description: string; icon?: string };

const CELL_TONES = [
  "bg-secondary text-secondary-foreground",
  "bg-muted text-foreground",
  "bg-accent/10 text-foreground",
  "bg-primary/5 text-foreground",
  "bg-secondary text-secondary-foreground",
];

export function FeatureBentoAsymmetric(props: RenderProps) {
  const features = props.modules.features as { title?: string; items?: FeatureItem[] } | null;
  const items = features?.items ?? [];
  if (items.length < 4) return null;
  const hero = items[0];
  const rest = items.slice(1, 6);

  return (
    <section className="border-b border-border">
      <div className="container py-20 lg:py-28">
        {/* Section header — keep it minimal, not a giant marketing block */}
        <div className="mb-12 lg:mb-16 max-w-2xl">
          <p className="font-mark text-xs uppercase tracking-[0.22em] text-muted-foreground mb-4">
            Что мы делаем
          </p>
          <h2 className="font-display text-4xl md:text-5xl tracking-tight text-balance">
            {features?.title ?? "Услуги, которые работают на вас"}
          </h2>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 lg:grid-rows-2 gap-3">
          {/* HERO CELL — span 2x2 on desktop */}
          <article className="lg:col-span-2 lg:row-span-2 relative p-8 lg:p-12 rounded-md border border-border bg-gradient-to-br from-primary/8 via-background to-accent/5 overflow-hidden">
            {hero.icon && (
              <div className="text-4xl mb-6" aria-hidden="true">
                {hero.icon}
              </div>
            )}
            <h3 className="font-display text-3xl md:text-4xl font-medium tracking-tight mb-4 text-balance">
              {hero.title}
            </h3>
            <p className="text-base lg:text-lg text-muted-foreground leading-relaxed max-w-md">
              {hero.description}
            </p>
            {/* Decorative number — top-right corner */}
            <div
              aria-hidden="true"
              className="absolute top-6 right-8 font-display text-xs text-muted-foreground/60"
            >
              01 /
            </div>
          </article>

          {/* SMALLER CELLS */}
          {rest.map((it, i) => (
            <article
              key={i}
              className={`relative p-6 lg:p-7 rounded-md border border-border ${CELL_TONES[i % CELL_TONES.length]}`}
            >
              {it.icon && (
                <div className="text-2xl mb-3" aria-hidden="true">
                  {it.icon}
                </div>
              )}
              <h3 className="font-display text-lg lg:text-xl font-medium tracking-tight mb-2">
                {it.title}
              </h3>
              <p className="text-sm leading-relaxed opacity-80">{it.description}</p>
              <div
                aria-hidden="true"
                className="absolute top-3 right-4 font-mark text-[10px] uppercase tracking-wider opacity-50"
              >
                {String(i + 2).padStart(2, "0")} /
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
