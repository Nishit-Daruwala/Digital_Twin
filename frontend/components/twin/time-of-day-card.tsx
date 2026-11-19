import { Clock3 } from "lucide-react";
import { SLOTS, SLOT_LABEL } from "@/lib/slots";
import type { Accuracy, Insight, Prediction } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { VIZ } from "./viz";

const ROWS = [
  { target: "mood", label: "Mood", color: VIZ.mood },
  { target: "energy", label: "Energy", color: VIZ.energy },
] as const;

/**
 * Tomorrow by part of the day: the daily prediction plus the person's usual offset for each
 * slot (learned only from days with 2+ check-ins). Small multiples: one row per measure,
 * one hue per row; the row label carries identity, values are printed, so colour is never
 * the only cue.
 */
export function TimeOfDayCard({
  daily,
  rhythm,
  accuracy,
}: {
  daily: Prediction[];
  rhythm: Insight[];
  accuracy: Accuracy;
}) {
  const rows = ROWS.map((r) => ({
    ...r,
    tod: daily.find((p) => p.target === r.target)?.explanation.time_of_day,
  })).filter((r) => r.tod?.learned);

  if (!rows.length) {
    return (
      <Card className="flex animate-fade-up items-start gap-3 p-5 text-sm">
        <Clock3 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <p className="text-muted-foreground">
          <span className="font-medium text-foreground">Tomorrow by time of day</span> appears
          once you sometimes check in more than once a day (morning, afternoon, evening). Your
          twin then learns how your energy and mood usually move through the day.
        </p>
      </Card>
    );
  }

  const slotAcc = accuracy.by_slot;
  return (
    <Card className="animate-fade-up p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold">Tomorrow by time of day</h2>
        <span className="text-xs text-muted-foreground">
          Daily prediction + your usual rhythm
        </span>
      </div>

      <table className="w-full table-fixed text-sm">
        <caption className="sr-only">Predicted mood and energy tomorrow, by part of the day</caption>
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th className="w-20 pb-2 font-medium" scope="col">
              <span className="sr-only">Measure</span>
            </th>
            {SLOTS.map((s) => (
              <th key={s} scope="col" className="pb-2 font-medium">
                {SLOT_LABEL[s]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const vals = SLOTS.map((s) => r.tod!.slots[s].value);
            const best = Math.max(...vals);
            return (
              <tr key={r.target}>
                <th scope="row" className="py-2 pr-2 text-left text-[13px] font-semibold">
                  {r.label}
                </th>
                {SLOTS.map((s) => {
                  const v = r.tod!.slots[s].value;
                  return (
                    <td key={s} className="py-2 pr-3">
                      <div className="flex items-baseline gap-1">
                        <span
                          className={cn(
                            "font-mono text-[15px] tabular-nums",
                            v === best ? "font-semibold" : "text-muted-foreground",
                          )}
                        >
                          {v.toFixed(1)}
                        </span>
                        <span className="text-[11px] text-muted-foreground">/5</span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-secondary" aria-hidden>
                        <div
                          className="h-full rounded-full transition-[width] duration-500 ease-out"
                          style={{ width: `${((v - 1) / 4) * 100}%`, background: r.color }}
                        />
                      </div>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="mt-4 flex flex-col gap-1.5 border-t pt-3 text-xs text-muted-foreground">
        {rhythm.map((i) => (
          <p key={i.id} className="text-[13px] text-foreground">
            {i.text}
          </p>
        ))}
        {slotAcc && slotAcc.n > 0 && slotAcc.accuracy != null && (
          <p>
            Time-of-day predictions: {Math.round(slotAcc.accuracy * 100)}% within ½ point of your
            check-in in that slot ({slotAcc.n} checked).
          </p>
        )}
      </div>
    </Card>
  );
}
