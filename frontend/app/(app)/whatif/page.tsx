"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, FlaskConical, Minus, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { qk } from "@/lib/hooks";
import { SLOTS, SLOT_LABEL } from "@/lib/slots";
import type { WhatIfControl, WhatIfResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormError } from "@/components/ui/alert";
import { Skeleton, Spinner } from "@/components/spinner";
import { ShapBars } from "@/components/twin/shap-bars";
import { MODEL_LABEL, TARGET_LABEL } from "@/components/twin/viz";

const DEBOUNCE_MS = 180;

function fmt(c: WhatIfControl, v: number) {
  if (c.unit === "h") return `${v.toFixed(2).replace(/\.?0+$/, "")} h`;
  if (c.unit === "min") return v >= 60 ? `${Math.floor(v / 60)}h ${String(v % 60).padStart(2, "0")}m` : `${v} min`;
  return `${v} ${v === 1 ? "task" : "tasks"}`;
}

export default function WhatIfPage() {
  const [values, setValues] = useState<Record<string, number>>({});
  const [debounced, setDebounced] = useState<Record<string, number>>({});
  useEffect(() => {
    const t = setTimeout(() => setDebounced(values), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [values]);

  const changed = Object.keys(debounced).length > 0;
  const q = useQuery({
    queryKey: [...qk.whatif, debounced],
    queryFn: () => (changed ? api.simulate(debounced) : api.whatif()),
    placeholderData: keepPreviousData,
  });
  const d = q.data;

  return (
    <>
      <PageHeader
        eyebrow="Simulator"
        title="What if…"
        description="Change tonight and tomorrow's plan and see how your twin's prediction for tomorrow moves. Based on patterns in your own data, not a guarantee."
      />
      <FormError message={q.error?.message} className="mb-6" />

      {!d ? (
        <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      ) : d.note ? (
        <Card className="flex animate-fade-up items-start gap-4 p-6">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary">
            <FlaskConical className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <p className="font-semibold">Nothing to simulate yet</p>
            <p className="mt-1 max-w-xl text-sm leading-relaxed text-muted-foreground">{d.note}</p>
            <Button asChild size="sm" className="mt-4">
              <Link href="/checkin">Do a check-in</Link>
            </Button>
          </div>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)] lg:items-start">
          <Card className="flex flex-col gap-6 p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-[15px] font-semibold">Your plan</h2>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setValues({})}
                disabled={!Object.keys(values).length}
              >
                <RotateCcw /> Reset
              </Button>
            </div>
            {d.controls.map((c) => {
              const v = values[c.key] ?? c.value;
              const set = c.key in values;
              return (
                <div key={c.key} className="flex flex-col gap-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <label htmlFor={c.key} className="text-[13px] font-semibold">
                      {c.label}
                    </label>
                    <span className={cn("font-mono text-sm", set ? "font-semibold text-primary" : "text-muted-foreground")}>
                      {fmt(c, v)}
                    </span>
                  </div>
                  <input
                    id={c.key}
                    type="range"
                    min={c.min}
                    max={c.max}
                    step={c.step}
                    value={v}
                    aria-valuetext={fmt(c, v)}
                    onChange={(e) => setValues((s) => ({ ...s, [c.key]: Number(e.target.value) }))}
                    className="w-full cursor-pointer accent-[hsl(var(--primary))]"
                  />
                  <div className="flex justify-between font-mono text-[11px] text-muted-foreground">
                    <span>{fmt(c, c.min)}</span>
                    <span>
                      {c.source === "planned" ? "your plan" : "your usual"}: {fmt(c, c.value)}
                    </span>
                    <span>{fmt(c, c.max)}</span>
                  </div>
                </div>
              );
            })}
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              Ranges are values you have actually had, so the twin never guesses beyond your own
              experience.
            </p>
          </Card>

          <div className="flex min-w-0 flex-col gap-4">
            <div className="grid gap-4 md:grid-cols-2">
              {Object.entries(d.results).map(([target, r]) => (
                <ResultCard key={target} target={target} r={r} />
              ))}
            </div>
            <p className="flex items-center gap-2 text-xs text-muted-foreground" aria-live="polite">
              {q.isFetching ? <Spinner className="h-3 w-3" /> : null}
              {q.isFetching ? "Updating…" : `Updated in ${d.ms} ms`}
            </p>
          </div>
        </div>
      )}
    </>
  );
}

function ResultCard({ target, r }: { target: string; r: WhatIfResult }) {
  const up = r.delta >= 0.05;
  const down = r.delta <= -0.05;
  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="eyebrow text-muted-foreground">{TARGET_LABEL[target] ?? target} · tomorrow</p>
        <span className="shrink-0 rounded-[4px] bg-secondary px-1.5 py-0.5 text-[11px] text-muted-foreground">
          {MODEL_LABEL[r.model_kind] ?? r.model_kind}
        </span>
      </div>
      <div className="flex items-end gap-3">
        <span key={r.value} className="animate-pop text-[40px] font-semibold leading-none">
          {r.value.toFixed(1)}
        </span>
        <span
          className={cn(
            "mb-1 flex items-center gap-0.5 rounded-md px-1.5 py-0.5 font-mono text-xs font-semibold",
            up && "bg-[#2a78d6]/10 text-[#1f5fae]",
            down && "bg-[#d54810]/10 text-[#b44a1f]",
            !up && !down && "bg-secondary text-muted-foreground",
          )}
        >
          {up ? <ArrowUp className="h-3 w-3" /> : down ? <ArrowDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
          {r.delta > 0 ? "+" : ""}
          {r.delta.toFixed(2)}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        {r.learned
          ? `vs ${r.baseline.toFixed(1)} with your plan as it is · likely ${r.low.toFixed(1)}–${r.high.toFixed(1)}`
          : "Predicted from your recent average, so these sliders don't change it."}
      </p>

      {r.time_of_day && (
        <div className="grid grid-cols-3 gap-2 border-t pt-3 text-center">
          {SLOTS.map((s) => (
            <div key={s}>
              <p className="text-[11px] text-muted-foreground">{SLOT_LABEL[s]}</p>
              <p className="font-mono text-sm font-semibold">{r.time_of_day!.slots[s].value.toFixed(1)}</p>
            </div>
          ))}
        </div>
      )}

      {r.contributors.length > 0 && (
        <div className="border-t pt-3">
          <p className="mb-3 text-xs font-semibold">Why</p>
          <ShapBars items={r.contributors} />
        </div>
      )}
    </Card>
  );
}
