"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Minus, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { qk } from "@/lib/hooks";
import {
  SLOTS,
  SLOT_LABEL,
  SLOT_QUESTION,
  SLOT_WINDOW,
  isFull,
  isSkipped,
  setSkipped,
  timeOf,
} from "@/lib/slots";
import type { Checkin, CheckinIn, Slot } from "@/lib/types";
import { cn, isoDate } from "@/lib/utils";
import { PageHeader } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Scale } from "@/components/ui/scale";
import { FormError } from "@/components/ui/alert";
import { Skeleton, Spinner } from "@/components/spinner";
import { PendingPredictions } from "@/components/twin/pending-card";

type Metric = "mood" | "energy" | "stress" | "focus";

const METRICS: { key: Metric; label: string; low: string; high: string }[] = [
  { key: "mood", label: "Mood", low: "Low", high: "Great" },
  { key: "energy", label: "Energy", low: "Drained", high: "Energised" },
  { key: "stress", label: "Stress", low: "Calm", high: "Very stressed" },
  { key: "focus", label: "Focus", low: "Scattered", high: "Laser" },
];
const QUICK: Metric[] = ["mood", "energy"];

const DEFAULTS = { mood: 3, energy: 3, stress: 3, focus: 3, sleep_hours: "7", note: "" };

function dayLabel(d: string, opts: Intl.DateTimeFormatOptions) {
  return new Date(`${d}T00:00`).toLocaleDateString(undefined, opts);
}

export default function CheckinPage() {
  const qc = useQueryClient();
  const localToday = isoDate();
  const weekAgo = isoDate(new Date(Date.now() - 6 * 864e5));

  const todayQ = useQuery({ queryKey: qk.checkinToday, queryFn: api.checkinToday });
  const today = todayQ.data?.date ?? localToday; // the server's view of the user's local day
  const recent = useQuery({
    queryKey: qk.checkins(weekAgo, today),
    queryFn: () => api.checkins(weekAgo, today),
  });

  const [date, setDate] = useState<string | null>(null);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [form, setForm] = useState(DEFAULTS);
  const [expanded, setExpanded] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [skips, setSkips] = useState(0); // re-render after (un)skipping

  const day = date ?? today;
  const isToday = day === today;
  const ofDay = (recent.data ?? []).filter((c) => c.date === day);
  const bySlot = Object.fromEntries(ofDay.map((c) => [c.slot, c])) as Partial<Record<Slot, Checkin>>;
  const started = (s: Slot) =>
    !isToday || (todayQ.data?.slots.find((x) => x.slot === s)?.started ?? true);
  const current = isToday ? (todayQ.data?.current_slot ?? null) : null;
  const active: Slot =
    slot ?? current ?? (SLOTS.find((s) => bySlot[s]) as Slot | undefined) ?? "evening";
  const existing = bySlot[active] ?? null;
  const fullElsewhere = ofDay.some((c) => c.slot !== active && isFull(c));
  const full = expanded || isFull(existing) || (!existing && !fullElsewhere);

  // Prefill from the saved check-in for this slot. Keyed on id + updated_at so a
  // background refetch doesn't wipe what the user is typing.
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
  }, [existingKey, day, active]);

  const save = useMutation({
    mutationFn: (body: CheckinIn) => api.saveCheckin(body),
    onSuccess: (c: Checkin) => {
      setSavedAt(c.updated_at);
      setSkipped(c.date, c.slot, false);
      qc.invalidateQueries({ queryKey: ["checkins"] });
      qc.invalidateQueries({ queryKey: ["predictions"] });
      qc.invalidateQueries({ queryKey: qk.dashboard });
    },
  });

  function pick(d: string | null, s: Slot | null) {
    setDate(d);
    setSlot(s);
    setExpanded(false);
    setSavedAt(null);
    save.reset();
  }

  function toggleSkip(s: Slot) {
    setSkipped(day, s, !isSkipped(day, s));
    setSkips((n) => n + 1);
  }

  const sleep = form.sleep_hours === "" ? null : Number(form.sleep_hours);
  const sleepInvalid = full && sleep !== null && (Number.isNaN(sleep) || sleep < 0 || sleep > 24);

  function stepSleep(delta: number) {
    const base = sleep === null || Number.isNaN(sleep) ? 7 : sleep;
    const v = Math.min(24, Math.max(0, Math.round((base + delta) * 2) / 2));
    setForm((f) => ({ ...f, sleep_hours: String(v) }));
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (sleepInvalid) return;
    const body: CheckinIn = {
      date: day,
      slot: active,
      mood: form.mood,
      energy: form.energy,
      note: form.note.trim() || null,
    };
    if (full) Object.assign(body, { stress: form.stress, focus: form.focus, sleep_hours: sleep });
    save.mutate(body);
  }

  const skipped = isToday && !existing && isSkipped(day, active);
  void skips;

  return (
    <>
      <PageHeader
        eyebrow={dayLabel(day, { weekday: "long", day: "numeric", month: "long" })}
        title={isToday ? SLOT_QUESTION[active] : `${SLOT_LABEL[active]} check-in`}
        description="Up to three check-ins a day: morning, afternoon and evening. Each one is optional; more than one a day teaches your twin your daily rhythm."
      />

      <PendingPredictions />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-4">
          <SlotStrip
            loading={todayQ.isLoading || recent.isLoading}
            day={day}
            isToday={isToday}
            active={active}
            current={current}
            bySlot={bySlot}
            started={started}
            onPick={(s) => pick(date, s)}
          />

          <Card>
            <form onSubmit={submit}>
              <div className="grid gap-x-10 gap-y-7 p-6 sm:grid-cols-2 md:p-7">
                {METRICS.filter((m) => full || QUICK.includes(m.key)).map((m) => (
                  <Scale
                    key={m.key}
                    label={m.label}
                    low={m.low}
                    high={m.high}
                    value={form[m.key]}
                    onChange={(v) => setForm((f) => ({ ...f, [m.key]: v }))}
                  />
                ))}

                {full && (
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
                    {sleepInvalid && (
                      <p className="text-xs text-destructive">Enter 0 to 24 hours.</p>
                    )}
                  </div>
                )}

                <div className="flex flex-col gap-2.5">
                  <Label htmlFor="date">Day</Label>
                  <Input
                    id="date"
                    type="date"
                    value={day}
                    max={today}
                    onChange={(e) => e.target.value && pick(e.target.value, null)}
                  />
                </div>

                <div className="flex flex-col gap-2.5 sm:col-span-2">
                  <Label htmlFor="note">One line about it (optional)</Label>
                  <Input
                    id="note"
                    maxLength={280}
                    placeholder="e.g. Productive morning, slumped after lunch"
                    value={form.note}
                    onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
                  />
                </div>

                {!full && (
                  <button
                    type="button"
                    onClick={() => setExpanded(true)}
                    className="flex w-fit items-center gap-1 text-sm font-medium text-primary hover:underline sm:col-span-2"
                  >
                    <ChevronDown className="h-4 w-4" aria-hidden /> Add sleep, stress and focus
                  </button>
                )}
              </div>

              <div className="flex flex-col gap-3 border-t bg-secondary/40 px-6 py-4 md:px-7">
                <FormError message={save.error?.message} />
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  <Button type="submit" disabled={save.isPending || sleepInvalid || !started(active)}>
                    {save.isPending && <Spinner className="text-primary-foreground" />}
                    {existing ? "Update" : full ? "Save check-in" : "Save quick check-in"}
                  </Button>
                  {isToday && !existing && (
                    <Button type="button" variant="ghost" onClick={() => toggleSkip(active)}>
                      {skipped ? "Undo skip" : `Skip this ${active}`}
                    </Button>
                  )}
                  {savedAt && !save.isPending ? (
                    <span
                      className="flex animate-fade-in items-center gap-1.5 text-sm font-medium text-success"
                      role="status"
                    >
                      <Check className="h-4 w-4 animate-pop" strokeWidth={3} aria-hidden /> Saved
                    </span>
                  ) : (
                    <span className="text-sm text-muted-foreground">
                      {skipped
                        ? "Skipped. No problem, your twin works with whatever you log."
                        : full
                          ? "Takes about 20 seconds."
                          : "Two taps: mood and energy."}
                    </span>
                  )}
                </div>
              </div>
            </form>
          </Card>
        </div>

        <Card className="h-fit">
          <div className="flex items-baseline justify-between px-5 pb-3 pt-5">
            <h2 className="text-[15px] font-semibold">Last 7 days</h2>
            <span className="text-xs text-muted-foreground">morning · afternoon · evening</span>
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
                  const d = isoDate(new Date(new Date(`${today}T12:00`).getTime() - i * 864e5));
                  const cs = (recent.data ?? []).filter((x) => x.date === d);
                  const selected = d === day;
                  return (
                    <li key={d}>
                      <button
                        type="button"
                        onClick={() => pick(d === today ? null : d, null)}
                        aria-current={selected ? "date" : undefined}
                        className={cn(
                          "flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors duration-150",
                          selected ? "bg-primary-soft" : "hover:bg-secondary",
                        )}
                      >
                        <span className={cn(selected && "font-semibold")}>
                          {i === 0
                            ? "Today"
                            : dayLabel(d, { weekday: "short", day: "numeric", month: "short" })}
                        </span>
                        <span
                          className="flex items-center gap-1.5"
                          aria-label={`${cs.length} of 3 check-ins`}
                        >
                          {SLOTS.map((s) => (
                            <span
                              key={s}
                              title={SLOT_LABEL[s]}
                              className={cn(
                                "h-2 w-2 rounded-full transition-colors",
                                cs.some((c) => c.slot === s) ? "bg-primary" : "border border-input",
                              )}
                            />
                          ))}
                        </span>
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

function SlotStrip({
  loading,
  day,
  isToday,
  active,
  current,
  bySlot,
  started,
  onPick,
}: {
  loading: boolean;
  day: string;
  isToday: boolean;
  active: Slot;
  current: Slot | null;
  bySlot: Partial<Record<Slot, Checkin>>;
  started: (s: Slot) => boolean;
  onPick: (s: Slot) => void;
}) {
  if (loading) return <Skeleton className="h-[74px]" />;
  return (
    <div className="grid grid-cols-3 gap-2" role="tablist" aria-label="Part of the day">
      {SLOTS.map((s) => {
        const c = bySlot[s];
        const open = started(s);
        const on = s === active;
        const status = c
          ? `${timeOf(c) ?? "Done"} · M${c.mood ?? "–"} E${c.energy ?? "–"}`
          : !open
            ? "Not yet"
            : isToday && isSkipped(day, s)
              ? "Skipped"
              : s === current
                ? "Now"
                : "Open";
        return (
          <button
            key={s}
            type="button"
            role="tab"
            aria-selected={on}
            disabled={!open}
            onClick={() => onPick(s)}
            className={cn(
              "flex min-w-0 flex-col items-start gap-0.5 rounded-lg border px-3 py-2.5 text-left transition-colors duration-150",
              on ? "border-primary bg-primary-soft" : "bg-card hover:bg-secondary",
              !open && "cursor-not-allowed opacity-55 hover:bg-card",
            )}
          >
            <span className="flex w-full items-center justify-between gap-1">
              <span className="text-sm font-semibold">{SLOT_LABEL[s]}</span>
              {c && <Check className="h-3.5 w-3.5 shrink-0 text-success" strokeWidth={3} aria-label="done" />}
            </span>
            <span className="truncate text-[11px] text-muted-foreground">{SLOT_WINDOW[s]}</span>
            <span
              className={cn(
                "truncate font-mono text-[11px]",
                s === current && !c ? "font-semibold text-primary" : "text-muted-foreground",
              )}
            >
              {status}
            </span>
          </button>
        );
      })}
    </div>
  );
}
