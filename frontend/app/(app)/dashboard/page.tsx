"use client";

import { LayoutGrid } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { Card } from "@/components/ui/card";
import { useMe } from "@/lib/hooks";

const TRAIT_NAMES: Record<string, string> = {
  chronotype: "Chronotype",
  optimism_bias: "Time estimates",
  planner: "Planning style",
  consistency: "Routine",
  stress_triggers: "Main stressor",
};

export default function DashboardPage() {
  const { data: me } = useMe();
  const traits = me
    ? Object.entries(me.profile.traits).filter(([k]) => k in TRAIT_NAMES)
    : [];

  return (
    <>
      <PageHeader eyebrow="Overview" title="Dashboard" />
      <div className="flex flex-col gap-8">
        {traits.length > 0 && (
          <section>
            <div className="mb-3 flex items-baseline justify-between">
              <h2 className="text-[15px] font-semibold">First impression</h2>
              <span className="eyebrow text-muted-foreground">From your quiz</span>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
              {traits.map(([key, t], i) => (
                <Card
                  key={key}
                  className="animate-fade-up p-4 transition-shadow duration-200 hover:shadow-lift"
                  style={{ animationDelay: `${i * 60}ms` }}
                >
                  <p className="eyebrow text-muted-foreground">{TRAIT_NAMES[key]}</p>
                  <p className="mt-2 text-[15px] font-semibold capitalize leading-snug">{t.label}</p>
                </Card>
              ))}
            </div>
          </section>
        )}
        <EmptyState
          icon={LayoutGrid}
          title="Insights and predictions are on their way"
          description="Your twin needs a few days of check-ins first. Patterns, predictions and charts appear here in a later phase."
        />
      </div>
    </>
  );
}
