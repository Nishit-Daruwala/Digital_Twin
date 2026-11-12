import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "./app-shell";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 aria-hidden className={cn("h-4 w-4 animate-spin text-muted-foreground", className)} />;
}

export function FullPageSpinner() {
  return (
    <div className="flex min-h-[70vh] items-center justify-center" role="status" aria-live="polite">
      <Logo className="h-8 w-8 animate-pulse" />
      <span className="sr-only">Loading…</span>
    </div>
  );
}

/** Placeholder block while data loads. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-secondary", className)} aria-hidden />;
}
