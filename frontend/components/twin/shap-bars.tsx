import { ArrowDown, ArrowUp } from "lucide-react";
import type { Contributor } from "@/lib/types";
import { VIZ } from "./viz";

/**
 * Top reasons behind a prediction (SHAP). Diverging bars from a centre line: blue raises,
 * tangerine lowers; the arrow + "raises/lowers" text carries the same meaning without colour.
 */
export function ShapBars({ items, unit = "points" }: { items: Contributor[]; unit?: string }) {
  if (!items.length) return null;
  const max = Math.max(...items.map((c) => Math.abs(c.impact)), 0.0001);
  return (
    <ul className="flex flex-col gap-2.5" aria-label="Reasons">
      {items.map((c) => {
        const up = c.direction === "up";
        const pct = (Math.abs(c.impact) / max) * 50;
        const amount =
          unit === "log-odds" ? "" : ` by ${Math.abs(c.impact).toFixed(Math.abs(c.impact) < 1 ? 2 : 1)}`;
        return (
          <li key={c.feature} className="flex flex-col gap-1">
            <div className="flex items-start justify-between gap-3 text-xs">
              <span className="min-w-0 flex-1 break-words leading-snug text-foreground">
                {c.label}
              </span>
              <span className="flex shrink-0 items-center gap-0.5 whitespace-nowrap font-mono text-[11px] text-muted-foreground">
                {up ? <ArrowUp className="h-3 w-3" aria-hidden /> : <ArrowDown className="h-3 w-3" aria-hidden />}
                {up ? "raises" : "lowers"}
                {amount}
              </span>
            </div>
            <div className="relative h-2 rounded-full bg-secondary" aria-hidden>
              <span className="absolute inset-y-[-2px] left-1/2 w-px bg-[#c3c2b7]" />
              <span
                className="absolute inset-y-0 rounded-full transition-[width] duration-500 ease-out"
                style={{
                  width: `${pct}%`,
                  background: up ? VIZ.up : VIZ.down,
                  left: up ? "50%" : `${50 - pct}%`,
                }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
