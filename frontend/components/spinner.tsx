import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 aria-hidden className={cn("h-5 w-5 animate-spin text-muted-foreground", className)} />;
}

export function FullPageSpinner() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center" role="status" aria-live="polite">
      <Spinner className="h-8 w-8" />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
