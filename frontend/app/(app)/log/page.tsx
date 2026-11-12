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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormError } from "@/components/ui/alert";
import { Spinner } from "@/components/spinner";

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

  return (
    <>
      <PageHeader
        title="Activity log"
        description="Plan tasks, tick them off, and log what you actually did."
      />

      <div className="mb-4 flex flex-col gap-2 sm:max-w-[200px]">
        <Label htmlFor="log-date">Day</Label>
        <Input
          id="log-date"
          type="date"
          value={date}
          onChange={(e) => e.target.value && setDate(e.target.value)}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <QuickAdd date={date} categories={categories} />

        <div className="flex flex-col gap-6">
          {list.isLoading ? (
            <Spinner />
          ) : list.error ? (
            <FormError message={list.error.message} />
          ) : list.data!.length === 0 ? (
            <EmptyState
              icon={ListChecks}
              title="Nothing logged for this day"
              description="Add what you plan to do, or what you already did. Your twin learns how your plans compare with reality."
            />
          ) : (
            <>
              <ActivityList title={`Planned (${planned.length})`} items={planned} date={date} />
              <ActivityList title={`Done (${done.length})`} items={done} date={date} />
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
      <CardHeader>
        <CardTitle className="text-base">Quick add</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div role="radiogroup" aria-label="Type" className="grid grid-cols-2 gap-1 rounded-lg bg-secondary p-1">
            {(["plan", "done"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={mode === m}
                onClick={() => setMode(m)}
                className={cn(
                  "rounded-md py-1.5 text-sm font-medium transition-colors",
                  mode === m ? "bg-background shadow-sm" : "text-muted-foreground",
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
            <legend className="mb-2 text-sm font-medium">Category</legend>
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
              <Label htmlFor="minutes">
                {mode === "plan" ? "Estimate (min)" : "Took (min)"}
              </Label>
              <Input
                id="minutes"
                type="number"
                inputMode="numeric"
                min={0}
                max={1440}
                step={5}
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
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
              />
            </div>
          </div>
          {minutesInvalid && (
            <p className="text-xs text-destructive">Minutes must be a whole number 0–1440.</p>
          )}

          <FormError message={add.error?.message} />
          <Button type="submit" disabled={!canSave || add.isPending}>
            {add.isPending && <Spinner className="text-primary-foreground" />}
            {mode === "plan" ? "Add to plan" : "Log it"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function ActivityList({ title, items, date }: { title: string; items: Activity[]; date: string }) {
  if (items.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col divide-y">
          {items.map((a) => (
            <ActivityRow key={a.id} activity={a} date={date} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function ActivityRow({ activity: a, date }: { activity: Activity; date: string }) {
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

  return (
    <li className="py-3">
      <div className="flex items-start gap-3">
        <button
          type="button"
          role="checkbox"
          aria-checked={a.completed}
          aria-label={a.completed ? `Mark "${a.title}" as not done` : `Mark "${a.title}" as done`}
          onClick={toggle}
          className={cn(
            "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            a.completed ? "border-primary bg-primary text-primary-foreground" : "border-input",
          )}
        >
          {a.completed && <Check className="h-3.5 w-3.5" aria-hidden />}
        </button>
        <div className="min-w-0 flex-1">
          <p className={cn("break-words text-sm font-medium", a.completed && "text-muted-foreground line-through")}>
            {a.title}
          </p>
          <p className="text-xs text-muted-foreground">
            {a.category}
            {a.start_time && ` · ${a.start_time.slice(0, 5)}`}
            {a.planned_min != null && ` · est. ${formatMinutes(a.planned_min)}`}
            {a.duration_min != null && ` · took ${formatMinutes(a.duration_min)}`}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground"
          aria-label={`Delete "${a.title}"`}
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
        >
          <Trash2 />
        </Button>
      </div>

      {confirming && (
        <form
          className="ml-8 mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (Number.isNaN(mins)) return;
            update.mutate({ completed: true, duration_min: mins });
            setConfirming(false);
          }}
        >
          <div className="flex flex-col gap-1">
            <Label htmlFor={`actual-${a.id}`} className="text-xs">
              How long did it actually take? (min)
            </Label>
            <Input
              id={`actual-${a.id}`}
              type="number"
              inputMode="numeric"
              min={0}
              max={1440}
              className="h-9 w-28"
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
      <FormError message={update.error?.message ?? remove.error?.message} className="ml-8 mt-2" />
    </li>
  );
}
