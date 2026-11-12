import * as React from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  selected?: boolean;
  /** Show a tick when selected (multi-select pickers). */
  tick?: boolean;
}

/** Toggleable option used for roles, goals, categories and quiz answers. */
export function Chip({ selected, tick = false, className, children, ...props }: ChipProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={cn(
        "inline-flex h-9 select-none items-center gap-1.5 rounded-md border px-3 text-[13px] font-medium transition-[background-color,border-color,color,transform] duration-150 ease-out active:scale-[0.96] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:opacity-40",
        selected
          ? "border-primary bg-primary-soft text-primary"
          : "border-input bg-card text-foreground hover:border-foreground/35",
        className,
      )}
      {...props}
    >
      {tick && selected && <Check className="h-3.5 w-3.5 animate-pop" strokeWidth={3} aria-hidden />}
      {children}
    </button>
  );
}
