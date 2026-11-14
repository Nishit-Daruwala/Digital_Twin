import { CheckSquare } from "lucide-react";
import type { Prediction } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { ShapBars } from "./shap-bars";
import { MODEL_LABEL } from "./viz";

/** Tomorrow's planned tasks with their chance of being finished: compact rows, full titles. */
export function TaskList({ tasks }: { tasks: Prediction[] }) {
  if (!tasks.length) return null;
  const kind = tasks[0].model_kind ?? "";
  const same = tasks.every((t) => t.model_kind === "rate");
  return (
    <Card className="animate-fade-up p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold">Tomorrow&apos;s tasks</h2>
        <span className="text-xs text-muted-foreground">
          {same
            ? "Based on how often you usually finish planned tasks"
            : `Chance of finishing · ${MODEL_LABEL[kind] ?? kind}`}
        </span>
      </div>
      <ul className="flex flex-col divide-y">
        {tasks.map((t) => {
          const pct = Math.round(t.predicted * 100);
          const reasons = t.explanation?.contributors ?? [];
          return (
            <li key={t.id} className="flex flex-col gap-2 py-3">
              <div className="flex items-center gap-3">
                <CheckSquare className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 flex-1 break-words text-sm font-medium">{t.task_title}</span>
                <div className="hidden h-1.5 w-24 rounded-full bg-secondary sm:block" aria-hidden>
                  <div className="h-full rounded-full bg-foreground/70" style={{ width: `${pct}%` }} />
                </div>
                <span className="w-12 text-right font-mono text-sm font-semibold">{pct}%</span>
              </div>
              {reasons.length > 0 && (
                <div className="pl-7">
                  <ShapBars items={reasons} unit={t.explanation.units} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
