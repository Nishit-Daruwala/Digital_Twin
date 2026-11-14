import { CheckSquare, Info } from "lucide-react";
import type { Prediction } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { ShapBars } from "./shap-bars";
import { MODEL_LABEL, TARGET_LABEL } from "./viz";

function word(v: number) {
  if (v < 1.75) return "very low";
  if (v < 2.5) return "low";
  if (v < 3.5) return "steady";
  if (v < 4.25) return "good";
  return "high";
}

export function PredictionCard({ p, index = 0 }: { p: Prediction; index?: number }) {
  const ex = p.explanation ?? {};
  const isTask = p.target === "task";
  const diff = p.baseline != null ? p.predicted - p.baseline : null;
  return (
    <Card
      className="flex animate-fade-up flex-col gap-4 p-5 transition-shadow duration-200 hover:shadow-lift"
      style={{ animationDelay: `${index * 70}ms` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow whitespace-nowrap text-muted-foreground">
            {isTask ? "Task" : TARGET_LABEL[p.target]} · tomorrow
          </p>
          {isTask && (
            <p className="mt-1 flex items-center gap-1.5 truncate text-sm font-semibold">
              <CheckSquare className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              {p.task_title}
            </p>
          )}
        </div>
        <span className="shrink-0 rounded-[4px] bg-secondary px-1.5 py-0.5 text-[11px] text-muted-foreground">
          {MODEL_LABEL[p.model_kind ?? ""] ?? p.model_kind}
        </span>
      </div>

      <div className="flex items-end gap-3">
        {isTask ? (
          <>
            <span className="text-[40px] font-semibold leading-none">{Math.round(p.predicted * 100)}%</span>
            <span className="pb-1 text-sm text-muted-foreground">chance you finish it</span>
          </>
        ) : (
          <>
            <span className="text-[40px] font-semibold leading-none">{p.predicted.toFixed(1)}</span>
            <div className="pb-1 text-sm leading-tight text-muted-foreground">
              <span className="font-medium text-foreground">{word(p.predicted)}</span>
              <br />
              {p.low != null && p.high != null && (
                <span className="whitespace-nowrap font-mono text-[11px]">
                  likely {p.low.toFixed(1)}–{p.high.toFixed(1)} of 5
                </span>
              )}
            </div>
          </>
        )}
      </div>

      {!isTask && diff != null && (
        <p className="text-xs text-muted-foreground">
          {Math.abs(diff) < 0.1
            ? "About the same as your 7-day average"
            : `${diff > 0 ? "Higher" : "Lower"} than your 7-day average (${p.baseline!.toFixed(1)})`}
        </p>
      )}

      <div className={cn("border-t pt-4", !ex.contributors?.length && "pb-0")}>
        {ex.contributors?.length ? (
          <>
            <p className="mb-3 text-xs font-semibold">
              Why
              {ex.start_from != null && (
                <span className="font-normal text-muted-foreground">
                  {" "}
                  · starting from your usual {ex.start_from.toFixed(1)}
                </span>
              )}
            </p>
            <ShapBars items={ex.contributors} unit={ex.units} />
          </>
        ) : (
          <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            {ex.summary ?? "Based on your recent history."}
          </p>
        )}
      </div>
    </Card>
  );
}
