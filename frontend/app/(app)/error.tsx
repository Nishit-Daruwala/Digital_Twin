"use client";

import { useEffect } from "react";
import { RotateCcw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Shown inside the app shell when a page crashes, so navigation keeps working. */
export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div role="alert" className="flex max-w-lg flex-col items-start gap-3 rounded-lg border bg-card p-6 shadow-card">
      <span className="flex h-10 w-10 items-center justify-center rounded-md bg-destructive/10 text-destructive">
        <TriangleAlert className="h-5 w-5" aria-hidden />
      </span>
      <h1 className="text-lg font-semibold">This page hit a problem</h1>
      <p className="text-sm leading-relaxed text-muted-foreground">
        Your data is safe. Try again, or open another page from the menu.
      </p>
      <Button size="sm" onClick={reset} className="mt-1">
        <RotateCcw /> Try again
      </Button>
    </div>
  );
}
