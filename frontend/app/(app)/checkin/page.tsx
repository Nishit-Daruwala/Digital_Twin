"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Minus, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { qk } from "@/lib/hooks";
import type { Checkin, CheckinIn } from "@/lib/types";
import { cn, isoDate } from "@/lib/utils";
import { PageHeader } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Scale } from "@/components/ui/scale";
import { FormError } from "@/components/ui/alert";
import { Skeleton, Spinner } from "@/components/spinner";

type Metric = "mood" | "energy" | "stress" | "focus";

const METRICS: { key: Metric; label: string; low: string; high: string }[] = [
  { key: "mood", label: "Mood", low: "Low", high: "Great" },
  { key: "energy", label: "Energy", low: "Drained", high: "Energised" },
  { key: "stress", label: "Stress", low: "Calm", high: "Very stressed" },
  { key: "focus", label: "Focus", low: "Scattered", high: "Laser" },
];

const DEFAULTS = { mood: 3, energy: 3, stress: 3, focus: 3, sleep_hours: "7", note: "" };

function dayLabel(d: string, opts: Intl.DateTimeFormatOptions) {
  return new Date(`${d}T00:00`).toLocaleDateString(undefined, opts);
}

export default function CheckinPage() {
  const qc = useQueryClient();
  const today = isoDate();
  const weekAgo = isoDate(new Date(Date.now() - 6 * 864e5));
  const [date, setDate] = useState(today);
  const [form, setForm] = useState(DEFAULTS);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const recent = useQuery({
    queryKey: qk.checkins(weekAgo, today),
    queryFn: () => api.checkins(weekAgo, today),
  });
  const existing = recent.data?.find((c) => c.date === date);

  // Prefill when a check-in already exists for the selected day.
  // Keyed on id + updated_at so a background refetch doesn't wipe what the user is typing.
  const existingKey = existing ? `${existing.id}:${existing.updated_at}` : "none";
  useEffect(() => {
    if (existing) {
      setForm({
        mood: existing.mood ?? 3,
        energy: existing.energy ?? 3,
        stress: existing.stress ?? 3,
        focus: existing.focus ?? 3,
        sleep_hours: existing.sleep_hours == null ? "" : String(existing.sleep_hours),
        note: existing.note ?? "",
      });
    } else {
      setForm(DEFAULTS);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingKey, date]);

  const save = useMutation({
    mutationFn: (body: CheckinIn) => api.saveCheckin(body),
    onSuccess: (c: Checkin) => {
      setSavedAt(c.updated_at);
      qc.invalidateQueries({ queryKey: ["checkins"] });
    },
  });

  function pickDate(d: string) {
    setDate(d);
    setSavedAt(null);
    save.reset();
  }

  const sleep = form.sleep_hours === "" ? null : Number(form.sleep_hours);
  const sleepInvalid = sleep !== null && (Number.isNaN(sleep) || sleep < 0 || sleep > 24);

  function stepSleep(delta: number) {
    const base = sleep === null || Number.isNaN(sleep) ? 7 : sleep;
    const v = Math.min(24, Math.max(0, Math.round((base + delta) * 2) / 2));
    setForm((f) => ({ ...f, sleep_hours: String(v) }));
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (sleepInvalid) return;
    save.mutate({
      date,
      mood: form.mood,
      energy: form.energy,
      stress: form.stress,
      focus: form.focus,
      sleep_hours: sleep,
      note: form.note.trim() || null,
    });
  }

  const isToday = date === today;

  return (
    <>
      <PageHeader
        eyebrow={dayLabel(date, { weekday: "long", day: "numeric", month: "long" })}
        title={isToday ? "How was today?" : "Check-in"}
        description="Takes about 20 seconds. One per day. Saving again updates it."
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <Card>
          <form onSubmit={submit}>
            <div className="grid gap-x-10 gap-y-7 p-6 sm:grid-cols-2 md:p-7">
              {METRICS.map((m) => (
                <Scale
                  key={m.key}
                  label={m.label}
                  low={m.low}
                  high={m.high}
                  value={form[m.key]}
                  onChange={(v) => setForm((f) => ({ ...f, [m.key]: v }))}
                />
              ))}

              <div className="flex flex-col gap-2.5">
                <Label htmlFor="sleep">Sleep last night (hours)</Label>
                <div className="flex items-center gap-1.5">
                  <Button
                    type="button"
                    variant="outline"
                    className="h-11 w-11 shrink-0 px-0"
                    onClick={() => stepSleep(-0.5)}
                    aria-label="Less sleep"
                  >
                    <Minus />
                  </Button>
                  <Input
                    id="sleep"
                    type="number"
                    inputMode="decimal"
                    min={0}
                    max={24}
                    step={0.5}
                    className="text-center font-mono"
                    value={form.sleep_hours}
                    aria-invalid={sleepInvalid}
                    onChange={(e) => setForm((f) => ({ ...f, sleep_hours: e.target.value }))}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    className="h-11 w-11 shrink-0 px-0"
                    onClick={() => stepSleep(0.5)}
                    aria-label="More sleep"
                  >
                    <Plus />
                  </Button>
                </div>
                {sleepInvalid && <p className="text-xs text-destructive">Enter 0 to 24 hours.</p>}
              </div>

              <div className="flex flex-col gap-2.5">
                <Label htmlFor="date">Day</Label>
                <Input
                  id="date"
                  type="date"
                  value={date}
                  max={today}
                  onChange={(e) => e.target.value && pickDate(e.target.value)}
                />
              </div>

              <div className="flex flex-col gap-2.5 sm:col-span-2">
                <Label htmlFor="note">One line about today (optional)</Label>
                <Input
                  id="note"
                  maxLength={280}
                  placeholder="e.g. Productive morning, slumped after lunch"
                  value={form.note}
                  onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
                />
              </div>
            </div>

            <div className="flex flex-col gap-3 border-t bg-secondary/40 px-6 py-4 md:px-7">
              <FormError message={save.error?.message} />
              <div className="flex items-center gap-4">
                <Button type="submit" disabled={save.isPending || sleepInvalid}>
                  {save.isPending && <Spinner className="text-primary-foreground" />}
                  {existing ? "Update check-in" : "Save check-in"}
                </Button>
                {savedAt && !save.isPending ? (
                  <span
                    className="flex animate-fade-in items-center gap-1.5 text-sm font-medium text-success"
                    role="status"
                  >
                    <Check className="h-4 w-4 animate-pop" strokeWidth={3} aria-hidden /> Saved
                  </span>
                ) : (
                  existing && (
                    <span className="text-sm text-muted-foreground">
                      You already checked in for this day.
                    </span>
                  )
                )}
              </div>
            </div>
          </form>
        </Card>

        <Card className="h-fit">
          <div className="flex items-baseline justify-between px-5 pb-3 pt-5">
            <h2 className="text-[15px] font-semibold">Last 7 days</h2>
            <span className="font-mono text-xs text-muted-foreground">
              {recent.data?.length ?? 0}/7
            </span>
          </div>
          <div className="px-2 pb-3">
            {recent.isLoading ? (
              <div className="flex flex-col gap-2 px-3 pb-2">
                {Array.from({ length: 7 }, (_, i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : (
              <ul className="flex flex-col">
                {Array.from({ length: 7 }, (_, i) => {
                  const d = isoDate(new Date(Date.now() - i * 864e5));
                  const c = recent.data?.find((x) => x.date === d);
                  const selected = d === date;
                  return (
                    <li key={d}>
                      <button
                        type="button"
                        onClick={() => pickDate(d)}
                        aria-current={selected ? "date" : undefined}
                        className={cn(
                          "flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors duration-150",
                          selected ? "bg-primary-soft" : "hover:bg-secondary",
                        )}
                      >
                        <span className={cn("flex items-center gap-2.5", selected && "font-semibold")}>
                          <span
                            className={cn(
                              "h-2 w-2 rounded-full transition-colors",
                              c ? "bg-primary" : "border border-input",
                            )}
                            aria-hidden
                          />
                          {i === 0 ? "Today" : dayLabel(d, { weekday: "short", day: "numeric", month: "short" })}
                        </span>
                        {c ? (
                          <span className="font-mono text-xs text-muted-foreground">
                            M{c.mood} · E{c.energy}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">No entry</span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </Card>
      </div>
    </>
  );
}
