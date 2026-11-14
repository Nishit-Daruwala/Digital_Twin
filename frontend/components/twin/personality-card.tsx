import { Database, ListChecks } from "lucide-react";
import type { Trait } from "@/lib/types";
import { Card } from "@/components/ui/card";

const NAMES: Record<string, string> = {
  chronotype: "Chronotype",
  optimism_bias: "Time estimates",
  planner: "Planning style",
  consistency: "Routine",
  stress_triggers: "Stress triggers",
  best_conditions: "Best focus days",
};

export function TraitBadge({ name, trait }: { name: string; trait: Trait & { detail?: string } }) {
  const fromData = trait.source === "data";
  const dots = Math.max(1, Math.round((trait.confidence ?? 0) * 5));
  return (
    <div className="flex flex-col gap-1.5 rounded-md border bg-background p-3.5">
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow text-muted-foreground">{NAMES[name] ?? name}</span>
        <span
          className="flex gap-0.5"
          role="img"
          aria-label={`Confidence ${Math.round((trait.confidence ?? 0) * 100)}%`}
        >
          {[1, 2, 3, 4, 5].map((n) => (
            <span key={n} className={n <= dots ? "h-1.5 w-1.5 rounded-full bg-foreground/70" : "h-1.5 w-1.5 rounded-full bg-border"} />
          ))}
        </span>
      </div>
      <p className="text-sm font-semibold leading-snug first-letter:uppercase">{trait.label}</p>
      {trait.detail && <p className="text-xs text-muted-foreground">{trait.detail}</p>}
      <p className="mt-auto flex items-center gap-1 text-[11px] text-muted-foreground">
        {fromData ? <Database className="h-3 w-3" aria-hidden /> : <ListChecks className="h-3 w-3" aria-hidden />}
        {fromData ? "From your data" : "From your quiz"}
      </p>
    </div>
  );
}

export function PersonalityCard({ traits }: { traits: Record<string, Trait & { detail?: string }> }) {
  const order = Object.keys(NAMES).filter((k) => traits[k]);
  if (!order.length) return null;
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-[15px] font-semibold">Personality</h2>
        <span className="text-xs text-muted-foreground">Updates as you log more days</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {order.map((k) => (
          <TraitBadge key={k} name={k} trait={traits[k]} />
        ))}
      </div>
    </Card>
  );
}
