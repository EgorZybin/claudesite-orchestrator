/**
 * PRICING PATTERN: 3-plan layout with middle highlighted via lift + ring
 *
 * WHEN TO USE:
 *   any site with `modules.pricing` containing 2-4 plans + exactly one with
 *   `highlighted: true`. Default for SaaS, consulting, agencies. Works
 *   across tones — the visual highlight pattern is universal.
 *
 * PATTERN HIGHLIGHTS:
 *   1. 3-column grid on desktop, stack on mobile
 *   2. Highlighted plan: `-translate-y-4 ring-2 ring-primary shadow-2xl`
 *      — visibly elevated above neighbors
 *   3. Highlighted plan ALSO uses inverse colors (`bg-foreground
 *      text-background`) so it pops as a "tile" against the page
 *   4. Each plan has: name (display font), price (display, oversized),
 *      period (mark font, lowercase), features list (hairline-divided),
 *      CTA button
 *   5. "Most popular" / similar tag on highlighted plan — positioned
 *      `absolute -top-3 right-6` for the "badge" feel
 *   6. Generous internal padding (`p-8`) and large gaps between plans
 *
 * GRACEFUL FALLBACKS:
 *   - no plans: returns null
 *   - no highlighted plan: still renders, just none lifted
 *   - 2 plans: switches to 2-col layout
 *   - 4 plans: switches to 4-col on lg, still single-highlighted
 */
import { Button } from "@/components/ui/button";
import { Check } from "lucide-react";
import type { RenderProps } from "@/types";

type Plan = {
  name: string;
  price: string;
  period?: string;
  features: string[];
  cta_label: string;
  cta_href: string;
  highlighted: boolean;
};

export function PricingEmphasizedMiddle(props: RenderProps) {
  const pricing = props.modules.pricing as { plans?: Plan[] } | null;
  const plans = pricing?.plans ?? [];
  if (plans.length === 0) return null;
  const colsClass =
    plans.length === 2 ? "lg:grid-cols-2"
    : plans.length === 4 ? "lg:grid-cols-4"
    : "lg:grid-cols-3";

  return (
    <section className="border-b border-border bg-secondary/40">
      <div className="container py-20 lg:py-28">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <p className="font-mark text-xs uppercase tracking-[0.22em] text-muted-foreground mb-4">
            Стоимость
          </p>
          <h2 className="font-display text-4xl md:text-5xl tracking-tight text-balance">
            Прозрачно. Без скрытых надбавок.
          </h2>
        </div>

        <div className={`grid grid-cols-1 ${colsClass} gap-6 lg:gap-8 max-w-6xl mx-auto`}>
          {plans.map((plan, i) => {
            const isHi = plan.highlighted;
            return (
              <div
                key={i}
                className={[
                  "relative rounded-lg border border-border p-8 lg:p-10",
                  "transition-transform",
                  isHi
                    ? "lg:-translate-y-6 ring-2 ring-primary shadow-2xl bg-foreground text-background border-foreground"
                    : "bg-background hover:-translate-y-1",
                ].join(" ")}
              >
                {isHi && (
                  <span className="absolute -top-3 right-6 bg-primary text-primary-foreground font-mark text-[10px] uppercase tracking-[0.2em] px-3 py-1.5 rounded">
                    Популярный
                  </span>
                )}
                <h3 className="font-display text-2xl font-medium tracking-tight mb-1">
                  {plan.name}
                </h3>
                <div className="flex items-baseline gap-2 mb-8">
                  <span className="font-display text-5xl lg:text-6xl font-medium tracking-tight">
                    {plan.price}
                  </span>
                  {plan.period && (
                    <span className={`font-mark text-sm lowercase ${isHi ? "opacity-60" : "text-muted-foreground"}`}>
                      / {plan.period}
                    </span>
                  )}
                </div>
                <ul className="space-y-3 mb-10">
                  {plan.features.map((f, fi) => (
                    <li key={fi} className="flex items-start gap-3 text-sm">
                      <Check
                        className={`w-4 h-4 mt-0.5 flex-shrink-0 ${isHi ? "text-primary-foreground/70" : "text-primary"}`}
                      />
                      <span className={isHi ? "text-background/90" : ""}>{f}</span>
                    </li>
                  ))}
                </ul>
                <Button
                  size="lg"
                  className="w-full"
                  variant={isHi ? "secondary" : "default"}
                  asChild
                >
                  <a href={plan.cta_href}>{plan.cta_label}</a>
                </Button>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
