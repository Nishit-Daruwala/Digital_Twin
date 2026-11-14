"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, BellRing, Info, RefreshCw, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { qk } from "@/lib/hooks";
import type { Dashboard } from "@/lib/types";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormError } from "@/components/ui/alert";
import { Skeleton, Spinner } from "@/components/spinner";
import { AccuracyRing } from "@/components/twin/accuracy-ring";
import { InsightCard } from "@/components/twin/insight-card";
import { PersonalityCard } from "@/components/twin/personality-card";
import { PredictionCard } from "@/components/twin/prediction-card";
import { TaskList } from "@/components/twin/task-list";
import { relativeTime } from "@/components/twin/viz";

// Charts (Recharts, ~100 kB) load after the rest of the dashboard is on screen.
const TrendChart = dynamic(() => import("@/components/twin/charts").then((m) => m.TrendChart), {
  ssr: false,
  loading: () => <Skeleton className="h-80" />,
});
const SleepChart = dynamic(() => import("@/components/twin/charts").then((m) => m.SleepChart), {
  ssr: false,
  loading: () => <Skeleton className="h-56" />,
});
const CategoryChart = dynamic(
  () => import("@/components/twin/charts").then((m) => m.CategoryChart),
  { ssr: false, loading: () => <Skeleton className="h-56" /> },
);

export default function DashboardPage() {
  const qc = useQueryClient();
  const dash = useQuery({ queryKey: qk.dashboard, queryFn: api.dashboard });
  const retrain = useMutation({
    mutationFn: api.retrain,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.dashboard });
      qc.invalidateQueries({ queryKey: qk.pending });
    },
  });
  const d = dash.data;
  const daily = d?.tomorrow.filter((p) => p.target !== "task") ?? [];
  const tasks = d?.tomorrow.filter((p) => p.target === "task") ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        description={d ? `Learned from ${d.data_days} days of your data.` : undefined}
        action={
          <div className="flex flex-col items-start gap-1 sm:items-end">
            <Button variant="outline" onClick={() => retrain.mutate()} disabled={retrain.isPending}>
              {retrain.isPending ? <Spinner /> : <RefreshCw />}
              {retrain.isPending ? "Updating your twin…" : "Update now"}
            </Button>
            <span className="text-[11px] text-muted-foreground">
              Last update {relativeTime(d?.last_run?.finished_at)} · runs nightly
            </span>
          </div>
        }
      />
      <FormError message={retrain.error?.message ?? dash.error?.message} className="mb-6" />

      {dash.isLoading || !d ? (
        <Loading />
      ) : (
        <div className="flex flex-col gap-8">
          {d.pending_count > 0 && (
            <Link
              href="/checkin"
              className="flex animate-fade-up items-center gap-3 rounded-lg border border-primary/25 bg-primary-soft/60 px-4 py-3 text-sm transition-colors hover:bg-primary-soft"
            >
              <BellRing className="h-4 w-4 shrink-0 text-primary" aria-hidden />
              <span className="flex-1">
                <strong>{d.pending_count} prediction{d.pending_count > 1 ? "s" : ""}</strong> to
                check. Confirm how the day went so your twin can learn.
              </span>
              <ArrowRight className="h-4 w-4 text-primary" aria-hidden />
            </Link>
          )}

          {d.anomalies.length > 0 && (
            <section aria-label="Unusual days" className="flex flex-col gap-2">
              {d.anomalies.map((a) => {
                // streaks and bad-direction spikes warn; a surprisingly *good* day is just a note
                const warn = a.evidence.kind !== "spike" || a.evidence.worse !== false;
                return (
                  <div
                    key={a.id}
                    className={cn(
                      "flex animate-fade-up items-start gap-3 rounded-lg border px-4 py-3 text-sm",
                      warn ? "border-[#ec835a]/40 bg-[#ec835a]/[0.07]" : "bg-secondary/60",
                    )}
                  >
                    {warn ? (
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#b44a1f]" aria-hidden />
                    ) : (
                      <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                    )}
                    <span>
                      <span className="sr-only">{warn ? "Heads-up: " : "Note: "}</span>
                      {a.text}
                    </span>
                  </div>
                );
              })}
            </section>
          )}

          {d.learning.phase === "learning" ? (
            <Learning d={d} />
          ) : (
            <section className="flex flex-col gap-4" aria-label="Tomorrow">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <AccuracyRing a={d.accuracy} />
                {daily.length ? (
                  daily.map((p, i) => <PredictionCard key={p.id} p={p} index={i + 1} />)
                ) : (
                  <Card className="p-5 text-sm text-muted-foreground xl:col-span-2">
                    No predictions for tomorrow yet. Press <strong>Update now</strong>, or check in
                    today so your twin has fresh data.
                  </Card>
                )}
              </div>
              <TaskList tasks={tasks} />
            </section>
          )}

          <section aria-labelledby="insights-h">
            <div className="mb-3 flex items-baseline justify-between">
              <h2 id="insights-h" className="text-[15px] font-semibold">What your twin noticed</h2>
              <span className="text-xs text-muted-foreground">Mined from your own data</span>
            </div>
            {d.insights.length ? (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {d.insights.map((i, n) => <InsightCard key={i.id} insight={i} index={n} />)}
              </div>
            ) : (
              <EmptyState
                icon={Sparkles}
                title="No strong patterns yet"
                description={
                  d.data_days < 14
                    ? "Patterns need about two weeks of check-ins. Keep logging; your twin only reports links that are statistically solid."
                    : "Your twin checked every pair of things you log and found no link strong enough to trust yet. That's an honest answer, not a bug."
                }
              />
            )}
          </section>

          <PersonalityCard traits={d.traits} />

          {d.series.length > 1 && (
            <section className="grid gap-4 lg:grid-cols-2 lg:items-start">
              <TrendChart data={d.series} />
              <div className="flex flex-col gap-4">
                <SleepChart data={d.series} />
                {d.minutes_by_category.length > 0 && <CategoryChart data={d.minutes_by_category} />}
              </div>
            </section>
          )}
        </div>
      )}
    </>
  );
}

function Learning({ d }: { d: Dashboard }) {
  const pct = (d.learning.days / d.learning.target) * 100;
  return (
    <Card className="animate-fade-up p-6">
      <p className="eyebrow text-primary">Your twin is learning</p>
      <p className="mt-2 text-xl font-semibold">
        {d.learning.days} of {d.learning.target} days
      </p>
      <div className="mt-3 h-2 rounded-full bg-secondary" role="progressbar"
           aria-valuemin={0} aria-valuemax={d.learning.target} aria-valuenow={d.learning.days}>
        <div className={cn("h-full rounded-full bg-primary transition-[width] duration-700 ease-out")}
             style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-3 text-sm text-muted-foreground">
        Predictions start after a few days of check-ins and get better every week. Patterns need
        about two weeks.
      </p>
      <Button asChild className="mt-4" size="sm">
        <Link href="/checkin">Do today&apos;s check-in</Link>
      </Button>
    </Card>
  );
}

function Loading() {
  return (
    <div className="flex flex-col gap-6" aria-busy>
      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <Skeleton className="h-52" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-52" />
          <Skeleton className="h-52" />
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Skeleton className="h-36" />
        <Skeleton className="h-36" />
        <Skeleton className="h-36" />
      </div>
    </div>
  );
}
