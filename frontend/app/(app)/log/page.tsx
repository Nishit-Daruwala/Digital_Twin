"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ListChecks, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useMe } from "@/lib/hooks";
import type { Activity, ActivityIn } from "@/lib/types";
import { cn, formatMinutes, isoDate } from "@/lib/utils";
import { PageHeader } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormError } from "@/components/ui/alert";
import { Skeleton, Spinner } from "@/components/spinner";

type Mode = "plan" | "done";

function parseMinutes(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isInteger(n) && n >= 0 && n <= 1440 ? n : NaN;
}

export default function LogPage() {
  const today = isoDate();
  const [date, setDate] = useState(today);
  const { data: me } = useMe();
  const categories = me?.profile.categories ?? [];

  const list = useQuery({
    queryKey: qk.activities(date, date),
    queryFn: () => api.activities(date, date),
  });
  const planned = list.data?.filter((a) => !a.completed) ?? [];
  const done = list.data?.filter((a) => a.completed) ?? [];
  const minutes = done.reduce((s, a) => s + (a.duration_min ?? 0), 0);

  return (
    <>
      <PageHeader
        eyebrow={new Date(`${date}T00:00`).toLocaleDateString(undefined, {
          weekday: "long",
          day: "numeric",
          month: "long",
        })}
        title="Activity log"
        description="Plan tasks, tick them off, and log what you actually did. Your twin compares plans with reality."
        action={
          <div className="flex flex-col gap-2 sm:w-[180px]">
            <Label htmlFor="log-date">Day</Label>
            <Input
              id="log-date"
              type="date"
              value={date}
              onChange={(e) => e.target.value && setDate(e.target.value)}
            />
          </div>
        }
      />

      <dl className="mb-6 grid grid-cols-3 divide-x rounded-lg border bg-card shadow-card">
        {[
          { k: "Planned", v: String(planned.length) },
          { k: "Done", v: String(done.length) },
          { k: "Logged", v: minutes ? formatMinutes(minutes) : "0m" },
        ].map((s) => (
          <div key={s.k} className="min-w-0 px-4 py-4 sm:px-6">
            <dt className="eyebrow truncate text-muted-foreground">{s.k}</dt>
            <dd className="mt-1.5 whitespace-nowrap text-xl font-semibold tabular-nums sm:text-2xl">
              {s.v}
            </dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <QuickAdd date={date} categories={categories} />

        <div className="flex flex-col gap-6">
          {list.isLoading ? (
            <Card className="flex flex-col gap-3 p-6">
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
            </Card>
          ) : list.error ? (
            <FormError message={list.error.message} />
          ) : list.data!.length === 0 ? (
            <EmptyState
              icon={ListChecks}
              title="Nothing logged for this day"
              description="Add what you plan to do, or what you already did. Over time your twin learns how long things really take you."
            />
          ) : (
            <>
              <ActivityList title="Planned" items={planned} date={date} />
              <ActivityList title="Done" items={done} date={date} />
            </>
          )}
        </div>
      </div>
    </>
  );
}

function QuickAdd({ date, categories }: { date: string; categories: string[] }) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>("plan");
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [minutes, setMinutes] = useState("");
  const [startTime, setStartTime] = useState("");

  const mins = parseMinutes(minutes);
  const minutesInvalid = Number.isNaN(mins);
  const canSave = title.trim() && category && !minutesInvalid;

  const add = useMutation({
    mutationFn: (body: ActivityIn) => api.createActivity(body),
    onSuccess: () => {
      setTitle("");
      setMinutes("");
      setStartTime("");
      qc.invalidateQueries({ queryKey: ["activities"] });
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSave) return;
    add.mutate({
      date,
      title: title.trim(),
      category,
      start_time: startTime || null,
      planned: mode === "plan",
      completed: mode === "done",
      planned_min: mode === "plan" ? mins : null,
      duration_min: mode === "done" ? mins : null,
    });
  }

  return (
    <Card className="h-fit">
      <form onSubmit={submit}>
        <div className="flex flex-col gap-5 p-6">
          <h2 className="text-[15px] font-semibold">Quick add</h2>

          <div
            role="radiogroup"
            aria-label="Type"
            className="relative grid grid-cols-2 rounded-md border bg-secondary p-1"
          >
            <span
              aria-hidden
              className={cn(
                "absolute bottom-1 top-1 w-[calc(50%-4px)] rounded-[5px] bg-card shadow-card transition-transform duration-300 ease-out",
                mode === "plan" ? "translate-x-0" : "translate-x-full",
              )}
              style={{ left: 4 }}
            />
            {(["plan", "done"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={mode === m}
                onClick={() => setMode(m)}
                className={cn(
                  "relative z-10 h-9 rounded-[5px] text-[13px] font-semibold transition-colors duration-200",
                  mode === m ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {m === "plan" ? "Plan a task" : "Log something done"}
              </button>
            ))}
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="title">What</Label>
            <Input
              id="title"
              maxLength={200}
              placeholder={mode === "plan" ? "e.g. Finish DBMS assignment" : "e.g. 5 km run"}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-[13px] font-semibold">Category</legend>
            <div className="flex flex-wrap gap-2">
              {categories.map((c) => (
                <Chip key={c} selected={category === c} onClick={() => setCategory(c)}>
                  {c}
                </Chip>
              ))}
            </div>
          </fieldset>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="minutes">{mode === "plan" ? "Estimate (min)" : "Took (min)"}</Label>
              <Input
                id="minutes"
                type="number"
                inputMode="numeric"
                min={0}
                max={1440}
                step={5}
                className="font-mono"
                value={minutes}
                aria-invalid={minutesInvalid}
                onChange={(e) => setMinutes(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="start">Start time</Label>
              <Input
                id="start"
                type="time"
                className="font-mono"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
              />
            </div>
          </div>
          {minutesInvalid && (
            <p className="-mt-2 text-xs text-destructive">Minutes must be a whole number 0–1440.</p>
          )}
          <FormError message={add.error?.message} />
        </div>
        <div className="border-t bg-secondary/40 px-6 py-4">
          <Button type="submit" className="w-full sm:w-auto" disabled={!canSave || add.isPending}>
            {add.isPending && <Spinner className="text-primary-foreground" />}
            {mode === "plan" ? "Add to plan" : "Log it"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ActivityList({ title, items, date }: { title: string; items: Activity[]; date: string }) {
  if (items.length === 0) return null;
  return (
    <Card className="animate-fade-up">
      <div className="flex items-baseline justify-between px-6 pb-1 pt-5">
        <h2 className="text-[15px] font-semibold">
          {title} ({items.length})
        </h2>
      </div>
      <ul className="flex flex-col divide-y px-6 pb-2">
        {items.map((a, i) => (
          <ActivityRow key={a.id} activity={a} date={date} index={i} />
        ))}
      </ul>
    </Card>
  );
}

function ActivityRow({
  activity: a,
  date,
  index,
}: {
  activity: Activity;
  date: string;
  index: number;
}) {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [actual, setActual] = useState(String(a.duration_min ?? a.planned_min ?? ""));
  const key = qk.activities(date, date);

  const update = useMutation({
    mutationFn: (body: { completed: boolean; duration_min?: number | null }) =>
      api.updateActivity(a.id, body),
    // Optimistic tick-off so the list feels instant.
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Activity[]>(key);
      qc.setQueryData<Activity[]>(key, (old) =>
        old?.map((x) => (x.id === a.id ? { ...x, ...body } : x)),
      );
      return { prev };
    },
    onError: (_e, _b, ctx) => ctx?.prev && qc.setQueryData(key, ctx.prev),
    onSettled: () => qc.invalidateQueries({ queryKey: ["activities"] }),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteActivity(a.id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["activities"] }),
  });

  const mins = parseMinutes(actual);

  function toggle() {
    if (a.completed) update.mutate({ completed: false });
    else setConfirming(true);
  }

  const over =
    a.completed && a.planned_min && a.duration_min != null && a.duration_min > a.planned_min;

  return (
    <li
      className={cn("group animate-fade-up py-3.5 transition-opacity", remove.isPending && "opacity-40")}
      style={{ animationDelay: `${index * 40}ms` }}
    >
      <div className="flex items-start gap-3.5">
        <button
          type="button"
          role="checkbox"
          aria-checked={a.completed}
          aria-label={a.completed ? `Mark "${a.title}" as not done` : `Mark "${a.title}" as done`}
          onClick={toggle}
          className={cn(
            "mt-0.5 flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-[5px] border-2 transition-[background-color,border-color,transform] duration-200 ease-out active:scale-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
            a.completed
              ? "border-primary bg-primary text-primary-foreground"
              : "border-input bg-card hover:border-primary",
          )}
        >
          {a.completed && <Check className="h-3.5 w-3.5 animate-pop" strokeWidth={3.2} aria-hidden />}
        </button>
        <div className="min-w-0 flex-1">
          <p
            className={cn(
              "break-words text-sm font-medium transition-colors duration-200",
              a.completed && "text-muted-foreground line-through decoration-foreground/30",
            )}
          >
            {a.title}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span className="rounded-[4px] bg-secondary px-1.5 py-0.5 font-medium text-foreground/80">
              {a.category}
            </span>
            {a.start_time && <span className="font-mono">{a.start_time.slice(0, 5)}</span>}
            {a.planned_min != null && <span>est. {formatMinutes(a.planned_min)}</span>}
            {a.duration_min != null && (
              <span className={cn(over && "font-medium text-primary")}>
                took {formatMinutes(a.duration_min)}
              </span>
            )}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground opacity-100 transition-opacity hover:text-destructive md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100"
          aria-label={`Delete "${a.title}"`}
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
        >
          <Trash2 />
        </Button>
      </div>

      {confirming && (
        <form
          className="ml-9 mt-3 flex animate-fade-up flex-wrap items-end gap-2 rounded-md border bg-secondary/50 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (Number.isNaN(mins)) return;
            update.mutate({ completed: true, duration_min: mins });
            setConfirming(false);
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`actual-${a.id}`} className="text-xs">
              How long did it actually take? (min)
            </Label>
            <Input
              id={`actual-${a.id}`}
              type="number"
              inputMode="numeric"
              min={0}
              max={1440}
              className="h-9 w-28 font-mono"
              autoFocus
              value={actual}
              onChange={(e) => setActual(e.target.value)}
            />
          </div>
          <Button type="submit" size="sm" disabled={Number.isNaN(mins)}>
            Done
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setConfirming(false)}>
            Cancel
          </Button>
        </form>
      )}
      <FormError message={update.error?.message ?? remove.error?.message} className="ml-9 mt-2" />
    </li>
  );
}
