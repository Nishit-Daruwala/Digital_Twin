import type { Accuracy } from "@/lib/types";
import { Card } from "@/components/ui/card";

/** The dashboard's one hero figure: how often the twin was within half a point. */
export function AccuracyRing({ a }: { a: Accuracy }) {
  const value = a.accuracy;
  const r = 44;
  const c = 2 * Math.PI * r;
  const frac = value ?? 0;
  const diff = value != null && a.baseline_accuracy != null ? value - a.baseline_accuracy : null;
  return (
    <Card className="flex animate-fade-up flex-col gap-4 p-5">
      <div>
        <p className="eyebrow text-muted-foreground">Twin accuracy · last 14 days</p>
      </div>
      <div className="flex items-center gap-5">
        <svg viewBox="0 0 100 100" className="h-28 w-28 shrink-0 -rotate-90" role="img"
             aria-label={value == null ? "No accuracy yet" : `Accuracy ${Math.round(frac * 100)} percent`}>
          <circle cx="50" cy="50" r={r} fill="none" strokeWidth="8" className="stroke-secondary" />
          <circle
            cx="50" cy="50" r={r} fill="none" strokeWidth="8" strokeLinecap="round"
            className="stroke-primary transition-[stroke-dashoffset] duration-700 ease-out"
            strokeDasharray={c} strokeDashoffset={c * (1 - frac)}
          />
        </svg>
        <div>
          <p className="text-5xl font-semibold leading-none">
            {value == null ? "–" : `${Math.round(frac * 100)}%`}
          </p>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
            {value == null
              ? "Appears once predictions can be checked against your check-ins."
              : `of ${a.n} predictions were within ½ point.`}
          </p>
        </div>
      </div>
      {diff != null && (
        <p className="border-t pt-3 text-xs text-muted-foreground">
          {diff > 0.005
            ? `${Math.round(diff * 100)} points better than guessing your 7-day average (${Math.round(a.baseline_accuracy! * 100)}%).`
            : diff < -0.005
              ? `${Math.round(-diff * 100)} points behind your 7-day average (${Math.round(a.baseline_accuracy! * 100)}%) so far.`
              : "On par with your 7-day average so far."}
          {a.backtest_share > 0 && " Includes back-tested days."}
        </p>
      )}
    </Card>
  );
}
