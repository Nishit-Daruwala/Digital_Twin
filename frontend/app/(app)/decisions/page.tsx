"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Plus, Signpost, Trash2, X } from "lucide-react";
import { api } from "@/lib/api";
import { qk } from "@/lib/hooks";
import type { Decision, DecisionIn } from "@/lib/types";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormError } from "@/components/ui/alert";
import { Skeleton, Spinner } from "@/components/spinner";

const OUTCOME = ["", "Bad", "Poor", "Okay", "Good", "Great"];

export default function DecisionsPage() {
  const list = useQuery({ queryKey: qk.decisions, queryFn: api.decisions });
  const all = list.data ?? [];
  const open = all.filter((d) => d.outcome_rating == null);
  const rated = all.filter((d) => d.outcome_rating != null);
  const avg = rated.length
    ? (rated.reduce((s, d) => s + d.outcome_rating!, 0) / rated.length).toFixed(1)
    : "—";

  return (
    <>
      <PageHeader
        eyebrow="Choices"
        title="Decisions"
        description="Log decisions, then rate how they turned out. Over time your twin learns which kinds of choices work for you."
      />

      <dl className="mb-6 grid grid-cols-3 divide-x rounded-lg border bg-card shadow-card">
        {[
          { k: "Logged", v: String(all.length) },
          { k: "Awaiting", v: String(open.length) },
          { k: "Avg outcome", v: avg },
        ].map((s) => (
          <div key={s.k} className="min-w-0 px-4 py-4 sm:px-6">
            <dt className="eyebrow truncate text-muted-foreground">{s.k}</dt>
            <dd className="mt-1.5 text-xl font-semibold tabular-nums sm:text-2xl">{s.v}</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <NewDecision />
        <div className="flex flex-col gap-6">
          {list.isLoading ? (
            <Card className="flex flex-col gap-3 p-6">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-16" />
            </Card>
          ) : list.error ? (
            <FormError message={list.error.message} />
          ) : all.length === 0 ? (
            <EmptyState
              icon={Signpost}
              title="No decisions yet"
              description="Add one here, or mention it in chat (e.g. “decided to skip the gym tonight”) and confirm the card."
            />
          ) : (
            <>
              <DecisionList title="Awaiting outcome" items={open} />
              <DecisionList title="Rated" items={rated} />
            </>
          )}
        </div>
      </div>
    </>
  );
}

function NewDecision() {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [options, setOptions] = useState<string[]>([]);
  const [optDraft, setOptDraft] = useState("");
  const [choice, setChoice] = useState("");
  const [reasoning, setReasoning] = useState("");

  const create = useMutation({
    mutationFn: (body: DecisionIn) => api.createDecision(body),
    onSuccess: () => {
      setText("");
      setOptions([]);
      setChoice("");
      setReasoning("");
      qc.invalidateQueries({ queryKey: qk.decisions });
    },
  });

  function addOption() {
    const v = optDraft.trim().slice(0, 120);
    if (v && !options.includes(v) && options.length < 8) setOptions([...options, v]);
    setOptDraft("");
  }

  return (
    <Card className="h-fit">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim()) return;
          create.mutate({
            text: text.trim(),
            options,
            choice: choice.trim() || null,
            reasoning: reasoning.trim() || null,
          });
        }}
      >
        <div className="flex flex-col gap-5 p-6">
          <h2 className="text-[15px] font-semibold">New decision</h2>
          <div className="flex flex-col gap-2">
            <Label htmlFor="d-text">What are you deciding?</Label>
            <Input
              id="d-text"
              maxLength={500}
              placeholder="e.g. Take the weekend internship?"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="d-opt">Options (optional)</Label>
            <div className="flex gap-2">
              <Input
                id="d-opt"
                maxLength={120}
                placeholder="Add an option, press Enter"
                value={optDraft}
                disabled={options.length >= 8}
                onChange={(e) => setOptDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addOption();
                  }
                }}
              />
              <Button type="button" variant="outline" className="h-11 w-11 shrink-0 px-0"
                aria-label="Add option" onClick={addOption} disabled={!optDraft.trim()}>
                <Plus />
              </Button>
            </div>
            {options.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {options.map((o) => (
                  <span
                    key={o}
                    className={cn(
                      "inline-flex h-8 animate-pop items-center rounded-md border text-[13px] font-medium transition-colors",
                      choice === o ? "border-primary bg-primary-soft text-primary" : "border-input",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => setChoice(choice === o ? "" : o)}
                      aria-pressed={choice === o}
                      className="h-full rounded-l-md pl-2.5 pr-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {o}
                    </button>
                    <button
                      type="button"
                      aria-label={`Remove option ${o}`}
                      onClick={() => {
                        setOptions(options.filter((x) => x !== o));
                        if (choice === o) setChoice("");
                      }}
                      className="flex h-full items-center rounded-r-md pr-2 opacity-60 hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="d-choice">What did you choose?</Label>
            <Input id="d-choice" maxLength={200} placeholder="Tap an option above or type it"
              value={choice} onChange={(e) => setChoice(e.target.value)} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="d-why">Why? (optional)</Label>
            <textarea
              id="d-why"
              rows={2}
              maxLength={1000}
              value={reasoning}
              onChange={(e) => setReasoning(e.target.value)}
              className="w-full resize-none rounded-md border border-input bg-card px-3.5 py-2.5 text-[15px] transition-[border-color,box-shadow] hover:border-foreground/30 focus-visible:border-primary focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/15 md:text-sm"
            />
          </div>
          <FormError message={create.error?.message} />
        </div>
        <div className="border-t bg-secondary/40 px-6 py-4">
          <Button type="submit" disabled={!text.trim() || create.isPending}>
            {create.isPending && <Spinner className="text-primary-foreground" />}
            Save decision
          </Button>
        </div>
      </form>
    </Card>
  );
}

function DecisionList({ title, items }: { title: string; items: Decision[] }) {
  if (!items.length) return null;
  return (
    <Card className="animate-fade-up">
      <h2 className="px-6 pb-1 pt-5 text-[15px] font-semibold">
        {title} ({items.length})
      </h2>
      <ul className="flex flex-col divide-y px-6 pb-2">
        {items.map((d, i) => (
          <DecisionRow key={d.id} d={d} index={i} />
        ))}
      </ul>
    </Card>
  );
}

function DecisionRow({ d, index }: { d: Decision; index: number }) {
  const qc = useQueryClient();
  const rate = useMutation({
    mutationFn: (r: number) => api.updateDecision(d.id, { outcome_rating: r }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.decisions }),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteDecision(d.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.decisions }),
  });

  return (
    <li
      className={cn("group animate-fade-up py-4", remove.isPending && "opacity-40")}
      style={{ animationDelay: `${index * 40}ms` }}
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="break-words text-sm font-semibold">{d.text}</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span className="font-mono">
              {new Date(d.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}
            </span>
            {d.source === "ai" && (
              <span className="inline-flex items-center gap-1 rounded-[4px] bg-primary-soft px-1.5 py-0.5 font-medium text-primary">
                <MessageSquare className="h-3 w-3" aria-hidden /> From chat
              </span>
            )}
            {d.options.map((o) => (
              <span
                key={o}
                className={cn(
                  "rounded-[4px] px-1.5 py-0.5",
                  o === d.choice ? "bg-foreground/[0.07] font-semibold text-foreground" : "bg-secondary",
                )}
              >
                {o}
              </span>
            ))}
            {d.choice && !d.options.includes(d.choice) && (
              <span className="rounded-[4px] bg-foreground/[0.07] px-1.5 py-0.5 font-semibold text-foreground">
                Chose: {d.choice}
              </span>
            )}
          </p>
          {d.reasoning && <p className="mt-2 text-sm text-muted-foreground">“{d.reasoning}”</p>}
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-destructive md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100"
          aria-label={`Delete "${d.text}"`}
          onClick={() => remove.mutate()}
          disabled={remove.isPending}
        >
          <Trash2 />
        </Button>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <span className="text-xs font-medium text-muted-foreground">How did it turn out?</span>
        <div role="group" aria-label={`Outcome for ${d.text}`} className="flex gap-1">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={d.outcome_rating === n}
              aria-label={`Outcome ${n} (${OUTCOME[n]})`}
              title={OUTCOME[n]}
              disabled={rate.isPending}
              onClick={() => rate.mutate(n)}
              className={cn(
                "h-8 w-8 rounded-[5px] border font-mono text-xs font-medium transition-colors duration-150 active:scale-95",
                d.outcome_rating === n
                  ? "border-primary bg-primary text-primary-foreground"
                  : d.outcome_rating != null && n < d.outcome_rating
                    ? "border-primary/30 bg-primary-soft text-primary"
                    : "border-input bg-card text-muted-foreground hover:border-foreground/35",
              )}
            >
              {n}
            </button>
          ))}
        </div>
        {d.outcome_rating != null && (
          <span className="text-xs font-medium">{OUTCOME[d.outcome_rating]}</span>
        )}
      </div>
      <FormError message={rate.error?.message ?? remove.error?.message} className="mt-2" />
    </li>
  );
}
