"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Target } from "lucide-react";
import { api } from "@/lib/api";
import { qk } from "@/lib/hooks";
import type { Prediction } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormError } from "@/components/ui/alert";
import { TARGET_LABEL, shortDate } from "./viz";

/** Morning card: "I predicted X for today — what was it?" Feeds the accuracy score. */
export function PendingPredictions() {
  const pending = useQuery({ queryKey: qk.pending, queryFn: api.predictionsPending });
  const [last, setLast] = useState<number | null>(null);
  const items = pending.data ?? [];
  if (!items.length && last == null) return null;
  return (
    <Card className="mb-6 animate-fade-up overflow-hidden">
      <div className="flex items-center gap-2 border-b bg-primary-soft/60 px-5 py-3">
        <Target className="h-4 w-4 text-primary" aria-hidden />
        <h2 className="text-[15px] font-semibold">How close was your twin?</h2>
      </div>
      {items.length ? (
        <ul className="divide-y">
          {items.map((p) => (
            <Row key={p.id} p={p} onDone={setLast} />
          ))}
        </ul>
      ) : (
        <p className="flex items-center gap-2 px-5 py-4 text-sm text-success">
          <Check className="h-4 w-4" strokeWidth={3} aria-hidden /> All checked.
          {last != null && ` Your twin's accuracy is now ${Math.round(last * 100)}%.`}
        </p>
      )}
    </Card>
  );
}

function Row({ p, onDone }: { p: Prediction; onDone: (acc: number | null) => void }) {
  const qc = useQueryClient();
  const isTask = p.target === "task";
  const [value, setValue] = useState<number | null>(p.suggested_actual);
  const confirm = useMutation({
    mutationFn: (v: number) => api.confirmPrediction(p.id, v),
    onSuccess: (r) => {
      onDone(r.accuracy.accuracy);
      qc.invalidateQueries({ queryKey: qk.pending });
      qc.invalidateQueries({ queryKey: qk.dashboard });
    },
  });
  const when = shortDate(p.for_date);
  return (
    <li className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="text-sm">
        <p className="font-medium">
          {isTask ? `Did you finish “${p.task_title}”?` : `${TARGET_LABEL[p.target]} on ${when}`}
        </p>
        <p className="text-xs text-muted-foreground">
          {isTask
            ? `I gave it a ${Math.round(p.predicted * 100)}% chance.`
            : `I predicted ${p.predicted.toFixed(1)}.`}
          {p.suggested_actual != null && " Pre-filled from your log."}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {isTask ? (
          [
            { v: 1, l: "Done" },
            { v: 0, l: "Not done" },
          ].map((o) => (
            <button key={o.v} type="button" aria-pressed={value === o.v} onClick={() => setValue(o.v)}
                    className={cn("h-9 rounded-md border px-3 text-[13px] font-medium transition-colors",
                      value === o.v ? "border-primary bg-primary text-primary-foreground" : "border-input hover:border-foreground/35")}>
              {o.l}
            </button>
          ))
        ) : (
          <div role="group" aria-label={`Actual ${p.target}`} className="flex gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} type="button" aria-pressed={value === n} aria-label={`${TARGET_LABEL[p.target]} was ${n}`}
                      onClick={() => setValue(n)}
                      className={cn("h-9 w-9 rounded-md border font-mono text-sm transition-colors",
                        value === n ? "border-primary bg-primary text-primary-foreground" : "border-input hover:border-foreground/35")}>
                {n}
              </button>
            ))}
          </div>
        )}
        <Button size="sm" disabled={value == null || confirm.isPending}
                onClick={() => value != null && confirm.mutate(value)}>
          Confirm
        </Button>
      </div>
      <FormError message={confirm.error?.message} className="sm:hidden" />
    </li>
  );
}
