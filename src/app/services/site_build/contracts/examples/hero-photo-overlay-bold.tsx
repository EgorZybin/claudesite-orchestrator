/**
 * HERO PATTERN: Full-bleed photo with gradient overlay + bottom-left bold text
 *
 * WHEN TO USE:
 *   warm-hospitality (restaurants, hotels, weddings), lifestyle, real-estate,
 *   anywhere `page.hero_image` exists and the brief asks for "photo-rich",
 *   "immersive", or "evocative" tone.
 *
 * PATTERN HIGHLIGHTS:
 *   1. Full-bleed `<picture>` with AVIF + WebP responsive sources
 *   2. Gradient overlay from `transparent` → `foreground/70` ensures
 *      AA-contrast for text without darkening the whole photo
 *   3. Content anchored bottom-left, NOT centered — magazine-cover feel
 *   4. Display font in inverse color (--background on photo) — strong
 *      contrast moment
 *   5. Single primary CTA — keep it punchy; no Secondary CTA clutter
 *   6. Small tag-row top-left with the brand/industry context
 *   7. Min viewport height 85vh on desktop, 70vh mobile — give the
 *      hero room to breathe but don't push content below the fold
 *
 * NOTE: degrades gracefully when `hero_image` is null — falls back to
 *   a solid-color hero with the same text composition, no broken visuals.
 */
import { Button } from "@/components/ui/button";
import type { RenderProps } from "@/types";

export function HeroPhotoOverlayBold(props: RenderProps) {
  const { page, site } = props;
  const img = page.hero_image;
  const avifSet = img
    ? img.replace(".webp", ".avif")
    : null;

  return (
    <section className="relative min-h-[70vh] lg:min-h-[85vh] overflow-hidden bg-foreground text-background">
      {img && (
        <picture className="absolute inset-0">
          {avifSet && (
            <source
              type="image/avif"
              srcSet={`${avifSet.replace("-1024", "-640")} 640w, ${avifSet.replace("-1024", "-960")} 960w, ${avifSet} 1280w`}
              sizes="100vw"
            />
          )}
          <source
            type="image/webp"
            srcSet={`${img.replace("-1024", "-640")} 640w, ${img.replace("-1024", "-960")} 960w, ${img} 1280w`}
            sizes="100vw"
          />
          <img
            src={img}
            alt={page.hero_title ?? page.title}
            loading="eager"
            decoding="async"
            className="w-full h-full object-cover"
          />
        </picture>
      )}

      {/* Gradient overlay — bottom is darker, top fades to transparent */}
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-gradient-to-b from-transparent via-foreground/20 to-foreground/75"
      />

      {/* Tag row top-left */}
      <div className="relative z-10 container pt-10">
        <p className="font-mark text-xs uppercase tracking-[0.24em] text-background/80">
          {site.brand} · {site.industry}
        </p>
      </div>

      {/* Bottom-left content */}
      <div className="relative z-10 container pb-16 lg:pb-24 mt-auto absolute bottom-0 left-1/2 -translate-x-1/2">
        <div className="max-w-3xl">
          <h1 className="font-display text-5xl md:text-6xl lg:text-7xl xl:text-8xl font-medium tracking-tight leading-[0.95] text-background text-balance mb-6">
            {page.hero_title ?? page.title}
          </h1>
          {page.hero_subtitle && (
            <p className="text-lg md:text-xl text-background/85 max-w-xl mb-8 leading-relaxed">
              {page.hero_subtitle}
            </p>
          )}
          <Button size="lg" variant="secondary" asChild>
            <a href="/contacts">Связаться</a>
          </Button>
        </div>
      </div>
    </section>
  );
}
