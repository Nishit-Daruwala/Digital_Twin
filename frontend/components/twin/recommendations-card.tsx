"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Lightbulb, ThumbsDown, ThumbsUp } from "lucide-react";
import { api } from "@/lib/api";
import { qk } from "@/lib/hooks";
import type { Recommendation, Recommendations } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { FormError } from "@/components/ui/alert";

/**
 * Tomorrow's suggestions (up to 3). 👍 keeps one and makes that kind of advice more likely;
 * 👎 replaces it right away and that kind becomes less likely (it won't come back for a week).
 */
export function RecommendationsCard() {
  const qc = useQueryClient();
  const recs = useQuery({ queryKey: qk.recommendations, queryFn: api.recommendations });
  const [open, setOpen] = useState<string | null>(null);
  const [showLearning, setShowLearning] = useState(false);
  const rate = useMutation({
    mutationFn: ({ id, value }: { id: string; value: 1 | -1 | 0 }) =>
      api.recommendationFeedback(id, value),
    onSuccess: (data: Recommendations) => qc.setQueryData(qk.recommendations, data),
  });

  const d = recs.data;
  if (!d || !d.items.length) return null;
  const rated = d.learning.filter((l) => l.likes + l.dislikes > 0);

  return (
    <Card className="animate-fade-up p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold">
          <Lightbulb className="h-4 w-4 text-primary" aria-hidden /> Suggestions for tomorrow
        </h2>
        <span className="text-xs text-muted-foreground">
          Your twin learns from your 👍 and 👎
        </span>
      </div>

      <ol className="flex flex-col divide-y">
        {d.items.map((r, i) => (
          <Item
            key={r.id}
            r={r}
            n={i + 1}
            open={open === r.id}
            onToggle={() => setOpen(open === r.id ? null : r.id)}
            busy={rate.isPending && rate.variables?.id === r.id}
            onRate={(value) => rate.mutate({ id: r.id, value })}
          />
        ))}
      </ol>
      <FormError message={rate.error?.message} className="mt-2" />

      {rated.length > 0 && (
        <div className="mt-3 border-t pt-3">
          <button
            type="button"
            onClick={() => setShowLearning((v) => !v)}
            aria-expanded={showLearning}
            className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <ChevronDown
              className={cn("h-3.5 w-3.5 transition-transform", showLearning && "rotate-180")}
              aria-hidden
            />
            What your twin has learned about your taste
          </button>
          {showLearning && (
            <ul className="mt-3 flex animate-fade-in flex-col gap-2" aria-label="Learned preferences">
              {d.learning.map((l) => (
                <li key={l.type} className="grid grid-cols-[minmax(0,1fr)_96px_64px] items-center gap-3 text-xs">
                  <span className="truncate">{l.label}</span>
                  <span className="h-1.5 rounded-full bg-secondary" aria-hidden>
                    <span
                      className="block h-full rounded-full bg-foreground/70 transition-[width] duration-500"
                      style={{ width: `${l.preference * 100}%` }}
                    />
                  </span>
                  <span className="text-right font-mono text-muted-foreground">
                    👍{l.likes} 👎{l.dislikes}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}

function Item({
  r,
  n,
  open,
  onToggle,
  busy,
  onRate,
}: {
  r: Recommendation;
  n: number;
  open: boolean;
  onToggle: () => void;
  busy: boolean;
  onRate: (v: 1 | -1 | 0) => void;
}) {
  const liked = r.feedback === 1;
  return (
    <li className="flex animate-fade-up gap-3 py-3">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary-soft font-mono text-xs font-semibold text-primary">
        {n}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-snug">{r.text}</p>
        {r.reason && (
          <>
            <button
              type="button"
              onClick={onToggle}
              aria-expanded={open}
              className="mt-1 text-xs font-medium text-primary hover:underline"
            >
              {open ? "Hide why" : "Why?"}
            </button>
            {open && (
              <p className="mt-1 animate-fade-in text-xs leading-relaxed text-muted-foreground">
                {r.reason}
              </p>
            )}
          </>
        )}
        {liked && (
          <p className="mt-1 text-xs text-success" role="status">
            Noted: more suggestions like this.
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-start gap-1">
        <button
          type="button"
          disabled={busy}
          onClick={() => onRate(liked ? 0 : 1)}
          aria-pressed={liked}
          aria-label="Helpful"
          title="Helpful"
          className={cn(
            "rounded-md p-2 transition-colors disabled:opacity-50",
            liked ? "bg-primary-soft text-primary" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
          )}
        >
          <ThumbsUp className="h-4 w-4" fill={liked ? "currentColor" : "none"} />
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onRate(-1)}
          aria-label="Not for me"
          title="Not for me (replace it)"
          className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
        >
          <ThumbsDown className="h-4 w-4" />
        </button>
      </div>
    </li>
  );
}
