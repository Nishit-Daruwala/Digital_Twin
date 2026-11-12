"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { api } from "@/lib/api";
import { qk } from "@/lib/hooks";
import type { Checkin, CheckinIn } from "@/lib/types";
import { cn, isoDate } from "@/lib/utils";
import { PageHeader } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { FormError } from "@/components/ui/alert";
import { Spinner } from "@/components/spinner";

type Metric = "mood" | "energy" | "stress" | "focus";

const METRICS: { key: Metric; label: string; low: string; high: string }[] = [
  { key: "mood", label: "Mood", low: "Low", high: "Great" },
  { key: "energy", label: "Energy", low: "Drained", high: "Energised" },
  { key: "stress", label: "Stress", low: "Calm", high: "Very stressed" },
  { key: "focus", label: "Focus", low: "Scattered", high: "Laser" },
];

const DEFAULTS = { mood: 3, energy: 3, stress: 3, focus: 3, sleep_hours: "7", note: "" };

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

  function pickDate(d: string) {
    setDate(d);
    setSavedAt(null);
    save.reset();
  }

  const sleep = form.sleep_hours === "" ? null : Number(form.sleep_hours);
  const sleepInvalid = sleep !== null && (Number.isNaN(sleep) || sleep < 0 || sleep > 24);

  const save = useMutation({
    mutationFn: (body: CheckinIn) => api.saveCheckin(body),
    onSuccess: (c: Checkin) => {
      setSavedAt(c.updated_at);
      qc.invalidateQueries({ queryKey: ["checkins"] });
    },
  });

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

  return (
    <>
      <PageHeader
        title="Daily check-in"
        description="Takes 20 seconds. One per day; saving again updates it."
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        <Card>
          <form onSubmit={submit} className="flex flex-col gap-6 p-5">
            <div className="flex flex-col gap-2 sm:max-w-[200px]">
              <Label htmlFor="date">Day</Label>
              <Input
                id="date"
                type="date"
                value={date}
                max={today}
                onChange={(e) => e.target.value && pickDate(e.target.value)}
              />
              {existing && (
                <p className="text-xs text-muted-foreground">Editing your saved check-in.</p>
              )}
            </div>

            {METRICS.map((m) => (
              <div key={m.key} className="flex flex-col gap-2">
                <div className="flex items-baseline justify-between">
                  <Label id={`${m.key}-label`}>{m.label}</Label>
                  <span className="text-sm font-semibold tabular-nums">{form[m.key]}/5</span>
                </div>
                <Slider
                  aria-labelledby={`${m.key}-label`}
                  aria-label={m.label}
                  min={1}
                  max={5}
                  step={1}
                  value={[form[m.key]]}
                  onValueChange={([v]) => setForm((f) => ({ ...f, [m.key]: v }))}
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{m.low}</span>
                  <span>{m.high}</span>
                </div>
              </div>
            ))}

            <div className="flex flex-col gap-2 sm:max-w-[200px]">
              <Label htmlFor="sleep">Sleep last night (hours)</Label>
              <Input
                id="sleep"
                type="number"
                inputMode="decimal"
                min={0}
                max={24}
                step={0.5}
                value={form.sleep_hours}
                aria-invalid={sleepInvalid}
                onChange={(e) => setForm((f) => ({ ...f, sleep_hours: e.target.value }))}
              />
              {sleepInvalid && <p className="text-xs text-destructive">Enter 0 to 24 hours.</p>}
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="note">One line about today (optional)</Label>
              <Input
                id="note"
                maxLength={280}
                placeholder="e.g. Productive morning, slumped after lunch"
                value={form.note}
                onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
              />
            </div>

            <FormError message={save.error?.message} />

            <div className="flex items-center gap-3">
              <Button type="submit" disabled={save.isPending || sleepInvalid}>
                {save.isPending && <Spinner className="text-primary-foreground" />}
                {existing ? "Update check-in" : "Save check-in"}
              </Button>
              {savedAt && !save.isPending && (
                <span className="flex items-center gap-1 text-sm text-success" role="status">
                  <Check className="h-4 w-4" aria-hidden /> Saved
                </span>
              )}
            </div>
          </form>
        </Card>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="text-base">Last 7 days</CardTitle>
          </CardHeader>
          <CardContent>
            {recent.isLoading ? (
              <Spinner />
            ) : (
              <ul className="flex flex-col gap-1">
                {Array.from({ length: 7 }, (_, i) => {
                  const d = isoDate(new Date(Date.now() - i * 864e5));
                  const c = recent.data?.find((x) => x.date === d);
                  return (
                    <li key={d}>
                      <button
                        type="button"
                        onClick={() => pickDate(d)}
                        className={cn(
                          "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent",
                          d === date && "bg-accent",
                        )}
                      >
                        <span>
                          {new Date(`${d}T00:00`).toLocaleDateString(undefined, {
                            weekday: "short",
                            day: "numeric",
                            month: "short",
                          })}
                        </span>
                        {c ? (
                          <span className="text-xs tabular-nums text-muted-foreground">
                            mood {c.mood} · energy {c.energy}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
