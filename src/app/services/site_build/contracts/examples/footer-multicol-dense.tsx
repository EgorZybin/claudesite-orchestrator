/**
 * FOOTER PATTERN: 5-col dense grid (brand+manifesto 2x + 3 link cols + bottom legal bar)
 *
 * WHEN TO USE:
 *   default site footer. Treats footer as a navigational + brand-recap zone,
 *   not an afterthought. Reads modules.footer.columns + modules.contact_info.
 *
 * PATTERN HIGHLIGHTS:
 *   1. INVERSE colors (`bg-foreground text-background`) — the footer becomes
 *      the structural "ground" of the page, big visual stop
 *   2. 5-column grid on desktop: brand block (2 cols, includes manifesto),
 *      then up to 3 link columns. Stacks 1-col on mobile, 2-col on tablet.
 *   3. Brand block: wordmark (display font, larger than nav-brand), short
 *      manifesto/tagline, then primary contact strip (email, phone)
 *   4. Link columns: tiny font-mark uppercase header + clean link list with
 *      hover state revealing accent color
 *   5. Bottom bar (`border-t border-background/15`): copyright on left,
 *      social/legal on right. Hairline border in inverse color.
 *   6. Large vertical padding (`py-20 lg:py-24`) — footer earns its
 *      presence
 *
 * GRACEFUL FALLBACKS:
 *   - no `columns`: brand block stretches full width
 *   - no `contact_info`: contact strip hidden
 *   - no `legal`: bottom bar shows only copyright
 */
import type { RenderProps } from "@/types";

type FooterColumn = { title: string; links: { label: string; href: string }[] };
type Social = { channel: string; href: string; label?: string };

export function FooterMulticolDense(props: RenderProps) {
  const footer = props.modules.footer as {
    tagline?: string;
    columns?: FooterColumn[];
    legal?: string;
  } | null;
  const contact = props.modules.contact_info as {
    email?: string;
    phone?: string;
    address?: string;
    social?: Social[];
  } | null;
  const cols = (footer?.columns ?? []).slice(0, 3);
  const year = new Date().getFullYear();

  return (
    <footer className="bg-foreground text-background">
      <div className="container py-20 lg:py-24">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-12 lg:gap-8">
          {/* BRAND BLOCK — spans 2 cols on lg */}
          <div className="lg:col-span-2">
            <p className="font-display text-2xl md:text-3xl tracking-tight mb-4">
              {props.site.brand}
            </p>
            {footer?.tagline && (
              <p className="text-base text-background/70 max-w-sm leading-relaxed mb-8">
                {footer.tagline}
              </p>
            )}

            {/* Contact strip */}
            {contact && (
              <div className="space-y-2 text-sm">
                {contact.email && (
                  <a
                    href={`mailto:${contact.email}`}
                    className="block text-background hover:text-accent transition-colors"
                  >
                    {contact.email}
                  </a>
                )}
                {contact.phone && (
                  <a
                    href={`tel:${contact.phone.replace(/[^+\d]/g, "")}`}
                    className="block text-background hover:text-accent transition-colors"
                  >
                    {contact.phone}
                  </a>
                )}
                {contact.address && (
                  <p className="text-background/70 max-w-xs">{contact.address}</p>
                )}
              </div>
            )}
          </div>

          {/* LINK COLUMNS */}
          {cols.map((col, i) => (
            <div key={i}>
              <p className="font-mark text-[10px] uppercase tracking-[0.22em] text-background/55 mb-5">
                {col.title}
              </p>
              <ul className="space-y-2.5">
                {col.links.map((lnk, li) => (
                  <li key={li}>
                    <a
                      href={lnk.href}
                      className="text-sm text-background/85 hover:text-accent transition-colors"
                    >
                      {lnk.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* BOTTOM BAR */}
        <div className="mt-16 lg:mt-20 pt-8 border-t border-background/15 flex flex-col sm:flex-row gap-4 justify-between items-start sm:items-center">
          <p className="font-mark text-xs text-background/55">
            © {year} {props.site.brand}. {footer?.legal ?? "Все права защищены."}
          </p>
          {contact?.social && contact.social.length > 0 && (
            <div className="flex gap-5">
              {contact.social.map((soc, si) => (
                <a
                  key={si}
                  href={soc.href}
                  className="font-mark text-xs uppercase tracking-[0.18em] text-background/70 hover:text-accent transition-colors"
                >
                  {soc.label ?? soc.channel}
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    </footer>
  );
}
