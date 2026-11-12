"use client";

import { cn } from "@/lib/utils";

/** 1–5 rating as five tappable segments. Faster and clearer than a slider on phones. */
export function Scale({
  label,
  value,
  onChange,
  low,
  high,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  low: string;
  high: string;
}) {
  const id = `scale-${label.toLowerCase()}`;
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-baseline justify-between">
        <span id={id} className="text-[13px] font-semibold">
          {label}
        </span>
        <span className="font-mono text-xs text-muted-foreground">
          <span key={value} className="inline-block animate-pop font-medium text-foreground">
            {value}
          </span>
          /5
        </span>
      </div>
      <div role="group" aria-labelledby={id} className="grid grid-cols-5 gap-1.5">
        {[1, 2, 3, 4, 5].map((n) => {
          const active = n === value;
          const filled = n <= value;
          return (
            <button
              key={n}
              type="button"
              aria-pressed={active}
              aria-label={`${label} ${n}`}
              onClick={() => onChange(n)}
              className={cn(
                "relative h-11 rounded-md border font-mono text-sm font-medium transition-[background-color,border-color,color,transform] duration-200 ease-out active:scale-[0.94] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : filled
                    ? "border-primary/30 bg-primary-soft text-primary"
                    : "border-input bg-card text-muted-foreground hover:border-foreground/35 hover:text-foreground",
              )}
            >
              {n}
            </button>
          );
        })}
      </div>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{low}</span>
        <span>{high}</span>
      </div>
    </div>
  );
}
