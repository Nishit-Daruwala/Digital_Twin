"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, Sparkles, X } from "lucide-react";
import { api } from "@/lib/api";
import type {
  CardActivity,
  CardCheckin,
  ChatMessage,
  ExtractionCard,
} from "@/lib/types";
import { cn, formatMinutes, isoDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormError } from "@/components/ui/alert";
import { Spinner } from "@/components/spinner";

const METRICS: { key: keyof CardCheckin; label: string }[] = [
  { key: "mood", label: "Mood" },
  { key: "energy", label: "Energy" },
  { key: "stress", label: "Stress" },
  { key: "focus", label: "Focus" },
];

function dayLabel(d: string) {
  const today = isoDate();
  const yesterday = isoDate(new Date(Date.now() - 864e5));
  if (d === today) return "Today";
  if (d === yesterday) return "Yesterday";
  return new Date(`${d}T00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** Summary chips for a saved / dismissed card. */
function summary(card: ExtractionCard): string[] {
  const out: string[] = [];
  const c = card.checkin;
  if (c.sleep_hours != null) out.push(`Sleep ${c.sleep_hours}h`);
  for (const m of METRICS) if (c[m.key] != null) out.push(`${m.label} ${c[m.key]}`);
  for (const a of card.activities)
    out.push(`${a.title}${a.duration_min != null ? ` · ${formatMinutes(a.duration_min)}` : ""}`);
  for (const d of card.decisions) out.push(`Decision: ${d.choice ?? d.text}`);
  return out;
}

export function ConfirmCard({
  message,
  categories,
  onUpdated,
}: {
  message: ChatMessage;
  categories: string[];
  onUpdated: (m: ChatMessage) => void;
}) {
  const qc = useQueryClient();
  const [card, setCard] = useState<ExtractionCard>(message.extraction!);
  const status = message.extraction_status;

  const confirm = useMutation({
    mutationFn: () => api.confirmExtraction(message.id, card),
    onSuccess: (res) => {
      onUpdated(res.message);
      for (const key of ["checkins", "activities", "decisions"])
        qc.invalidateQueries({ queryKey: [key] });
    },
  });
  const dismiss = useMutation({
    mutationFn: () => api.dismissExtraction(message.id),
    onSuccess: onUpdated,
  });
  const busy = confirm.isPending || dismiss.isPending;

  if (status !== "pending") {
    const saved = status === "confirmed";
    return (
      <div
        className={cn(
          "flex animate-fade-in flex-wrap items-center gap-2 rounded-lg border px-3.5 py-2.5 text-xs",
          saved ? "border-success/25 bg-success/[0.06]" : "bg-secondary/60 text-muted-foreground",
        )}
      >
        <span className={cn("flex items-center gap-1.5 font-semibold", saved && "text-success")}>
          {saved ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : <X className="h-3.5 w-3.5" />}
          {saved ? "Saved" : "Dismissed"}
        </span>
        {saved &&
          summary(message.extraction!).map((s) => (
            <span key={s} className="rounded-[4px] bg-card px-1.5 py-0.5 text-foreground/80">
              {s}
            </span>
          ))}
      </div>
    );
  }

  const setCheckin = (k: keyof CardCheckin, v: number | null) =>
    setCard((c) => ({ ...c, checkin: { ...c.checkin, [k]: v } }));
  const setActivity = (i: number, patch: Partial<CardActivity>) =>
    setCard((c) => ({
      ...c,
      activities: c.activities.map((a, j) => (j === i ? { ...a, ...patch } : a)),
    }));
  const removeActivity = (i: number) =>
    setCard((c) => ({ ...c, activities: c.activities.filter((_, j) => j !== i) }));
  const removeDecision = (i: number) =>
    setCard((c) => ({ ...c, decisions: c.decisions.filter((_, j) => j !== i) }));

  const shownMetrics = METRICS.filter((m) => card.checkin[m.key] != null);
  const sleep = card.checkin.sleep_hours;
  const sleepInvalid = sleep != null && (Number.isNaN(sleep) || sleep < 0 || sleep > 24);
  const minutesInvalid = card.activities.some(
    (a) => a.duration_min != null && (Number.isNaN(a.duration_min) || a.duration_min < 0 || a.duration_min > 1440),
  );
  const empty =
    shownMetrics.length === 0 && sleep == null && !card.activities.length && !card.decisions.length;

  const today = isoDate();
  const yesterday = isoDate(new Date(Date.now() - 864e5));

  return (
    <div className="w-full animate-fade-up overflow-hidden rounded-lg border border-primary/25 bg-card shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-primary-soft/60 px-4 py-2.5">
        <span className="flex items-center gap-1.5 text-[13px] font-semibold">
          <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden />
          Picked up from your message
        </span>
        <div role="radiogroup" aria-label="Which day" className="flex gap-1">
          {[today, yesterday].map((d) => (
            <button
              key={d}
              type="button"
              role="radio"
              aria-checked={card.date === d}
              onClick={() => setCard((c) => ({ ...c, date: d }))}
              className={cn(
                "rounded-[5px] px-2 py-0.5 text-xs font-medium transition-colors",
                card.date === d ? "bg-card text-foreground shadow-card" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {dayLabel(d)}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-4 p-4">
        {(shownMetrics.length > 0 || sleep != null) && (
          <section aria-label="Check-in" className="flex flex-col gap-2.5">
            <p className="eyebrow text-muted-foreground">
              Check-in
              {card.checkin.slot && <span className="normal-case"> · this {card.checkin.slot}</span>}
            </p>
            {sleep != null && (
              <Row label="Sleep" onRemove={() => setCheckin("sleep_hours", null)}>
                <Input
                  type="number"
                  inputMode="decimal"
                  aria-label="Sleep hours"
                  min={0}
                  max={24}
                  step={0.5}
                  className="h-9 w-24 font-mono"
                  value={Number.isNaN(sleep) ? "" : sleep}
                  aria-invalid={sleepInvalid}
                  onChange={(e) => setCheckin("sleep_hours", e.target.value === "" ? NaN : Number(e.target.value))}
                />
                <span className="text-xs text-muted-foreground">hours</span>
              </Row>
            )}
            {shownMetrics.map((m) => (
              <Row key={m.key} label={m.label} onRemove={() => setCheckin(m.key, null)}>
                <div role="group" aria-label={m.label} className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      type="button"
                      aria-pressed={card.checkin[m.key] === n}
                      aria-label={`${m.label} ${n}`}
                      onClick={() => setCheckin(m.key, n)}
                      className={cn(
                        "h-8 w-8 rounded-[5px] border font-mono text-xs font-medium transition-colors duration-150",
                        card.checkin[m.key] === n
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-input bg-card hover:border-foreground/35",
                      )}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </Row>
            ))}
          </section>
        )}

        {card.activities.length > 0 && (
          <section aria-label="Activities" className="flex flex-col gap-2.5">
            <p className="eyebrow text-muted-foreground">Activities</p>
            {card.activities.map((a, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <Input
                  aria-label="Activity title"
                  className="h-9 min-w-0 flex-1 basis-40"
                  value={a.title}
                  maxLength={200}
                  onChange={(e) => setActivity(i, { title: e.target.value })}
                />
                <select
                  aria-label="Category"
                  className="h-9 rounded-md border border-input bg-card px-2 text-sm focus-visible:border-primary focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/15"
                  value={a.category}
                  onChange={(e) => setActivity(i, { category: e.target.value })}
                >
                  {categories.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
                <Input
                  type="number"
                  inputMode="numeric"
                  aria-label="Minutes"
                  placeholder="min"
                  min={0}
                  max={1440}
                  className="h-9 w-20 font-mono"
                  value={a.duration_min == null || Number.isNaN(a.duration_min) ? "" : a.duration_min}
                  onChange={(e) =>
                    setActivity(i, { duration_min: e.target.value === "" ? null : Number(e.target.value) })
                  }
                />
                <button
                  type="button"
                  onClick={() => setActivity(i, { completed: !a.completed, planned: a.completed })}
                  className={cn(
                    "h-9 rounded-md border px-2.5 text-xs font-semibold transition-colors",
                    a.completed ? "border-success/30 bg-success/[0.07] text-success" : "border-input text-muted-foreground",
                  )}
                  aria-label={a.completed ? "Done (tap to mark as planned)" : "Planned (tap to mark as done)"}
                >
                  {a.completed ? "Done" : "Planned"}
                </button>
                <RemoveButton label={`Remove ${a.title}`} onClick={() => removeActivity(i)} />
              </div>
            ))}
          </section>
        )}

        {card.decisions.length > 0 && (
          <section aria-label="Decisions" className="flex flex-col gap-2.5">
            <p className="eyebrow text-muted-foreground">Decisions</p>
            {card.decisions.map((d, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input
                  aria-label="Decision"
                  className="h-9 flex-1"
                  value={d.text}
                  maxLength={500}
                  onChange={(e) =>
                    setCard((c) => ({
                      ...c,
                      decisions: c.decisions.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)),
                    }))
                  }
                />
                <RemoveButton label="Remove decision" onClick={() => removeDecision(i)} />
              </div>
            ))}
          </section>
        )}

        {empty && (
          <p className="text-sm text-muted-foreground">
            Everything removed. Dismiss this card, or undo by reloading.
          </p>
        )}

        <FormError message={confirm.error?.message ?? dismiss.error?.message} />
      </div>

      <div className="flex items-center justify-between gap-2 border-t bg-secondary/40 px-4 py-3">
        <p className="hidden text-xs text-muted-foreground sm:block">
          Nothing is saved until you confirm.
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => dismiss.mutate()}>
            Dismiss
          </Button>
          <Button
            size="sm"
            disabled={busy || empty || sleepInvalid || minutesInvalid || card.activities.some((a) => !a.title.trim())}
            onClick={() => confirm.mutate()}
          >
            {confirm.isPending ? <Spinner className="text-primary-foreground" /> : <Plus />}
            Confirm &amp; save
          </Button>
        </div>
      </div>
    </div>
  );
}

function Row({
  label,
  onRemove,
  children,
}: {
  label: string;
  onRemove: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-14 shrink-0 text-[13px] font-medium">{label}</span>
      <div className="flex flex-1 items-center gap-2">{children}</div>
      <RemoveButton label={`Remove ${label}`} onClick={onRemove} />
    </div>
  );
}

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <X className="h-4 w-4" />
    </button>
  );
}
