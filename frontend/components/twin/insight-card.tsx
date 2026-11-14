"use client";

import { HelpCircle, Sparkles } from "lucide-react";
import type { Insight } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { TARGET_LABEL, VIZ, shortDate } from "./viz";

const LAG = ["same day", "next day", "two days later"];

function fmtP(p?: number) {
  if (p == null) return "–";
  return p < 0.001 ? "< 0.001" : p.toFixed(3);
}

export function InsightCard({ insight: i, index = 0 }: { insight: Insight; index?: number }) {
  const e = i.evidence;
  const conf = Math.round((i.confidence ?? 0) * 100);
  return (
    <Card
      className="flex animate-fade-up flex-col gap-3 p-5 transition-shadow duration-200 hover:shadow-lift"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow flex items-center gap-1.5 text-muted-foreground">
          <Sparkles className="h-3 w-3 text-primary" aria-hidden />
          {TARGET_LABEL[e.target ?? ""] ?? "Pattern"} · {LAG[e.lag ?? 0]}
        </span>
        {i.is_new && (
          <span className="rounded-[4px] bg-primary-soft px-1.5 py-0.5 text-[11px] font-semibold text-primary">
            New
          </span>
        )}
        {e.fading && !i.is_new && (
          <span className="rounded-[4px] bg-secondary px-1.5 py-0.5 text-[11px] text-muted-foreground">
            Fading
          </span>
        )}
      </div>

      <p className="text-[15px] font-medium leading-snug">{i.text}</p>

      <div className="mt-auto flex items-center justify-between gap-3 pt-1">
        <div className="flex items-center gap-2" title={`Confidence ${conf}%`}>
          <div className="h-1.5 w-16 rounded-full bg-secondary" aria-hidden>
            <div className="h-full rounded-full bg-foreground/70" style={{ width: `${conf}%` }} />
          </div>
          <span className="text-[11px] text-muted-foreground">Confidence {conf}%</span>
        </div>
        <Popover>
          <PopoverTrigger className="flex items-center gap-1 rounded-md px-1.5 py-1 text-xs font-semibold text-primary transition-colors hover:bg-primary-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <HelpCircle className="h-3.5 w-3.5" aria-hidden /> Why?
          </PopoverTrigger>
          <PopoverContent>
            <Evidence i={i} />
          </PopoverContent>
        </Popover>
      </div>
    </Card>
  );
}

function Evidence({ i }: { i: Insight }) {
  const e = i.evidence;
  const worse = e.worse_mean ?? 0;
  const other = e.other_mean ?? 0;
  const max = Math.max(worse, other, 0.001);
  const pct = e.target === "completion_rate";
  const fmt = (v: number) => (pct ? `${Math.round(v * 100)}%` : v.toFixed(1));
  return (
    <div className="flex flex-col gap-3">
      <p className="font-semibold">How your twin found this</p>
      <p className="text-xs leading-relaxed text-muted-foreground">
        It compared every pair of things you log, across {e.n} days, and kept only links that
        stayed strong after correcting for the number of comparisons. A link is a pattern, not
        proof of cause.
      </p>
      <dl className="grid grid-cols-3 gap-2 rounded-md bg-secondary/60 p-2.5 text-center">
        {[
          { k: "Strength ρ", v: (e.r ?? 0).toFixed(2) },
          { k: "Adj. p", v: fmtP(e.p_adj) },
          { k: "Days", v: String(e.n ?? "–") },
        ].map((x) => (
          <div key={x.k}>
            <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{x.k}</dt>
            <dd className="font-mono text-sm font-medium">{x.v}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-col gap-2" aria-label="Average on each side">
        {[
          { label: `When it happens (${e.n_worse} days)`, v: worse, c: VIZ.down },
          { label: `Otherwise (${e.n_other} days)`, v: other, c: VIZ.up },
        ].map((r) => (
          <div key={r.label} className="flex flex-col gap-1">
            <div className="flex justify-between text-xs">
              <span>{r.label}</span>
              <span className="font-mono font-medium">{fmt(r.v)}</span>
            </div>
            <div className="h-2 rounded-full bg-secondary">
              <div className="h-full rounded-full" style={{ width: `${(r.v / max) * 100}%`, background: r.c }} />
            </div>
          </div>
        ))}
      </div>
      <p className={cn("text-[11px] text-muted-foreground")}>
        First seen {i.first_seen ? shortDate(i.first_seen) : "–"}
        {e.wording === "llm" ? " · wording by AI, numbers checked against the data" : ""}
      </p>
    </div>
  );
}
