"use client";

import { Suspense, useEffect, useRef } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { BellOff } from "lucide-react";
import { api } from "@/lib/api";
import { Wordmark } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/alert";
import { Spinner } from "@/components/spinner";

/** Target of the "Turn off reminders" link in the 8 PM email. No login needed: the signed
 *  token in the link can only switch reminders off. It POSTs, so link scanners can't. */
function TurnOff() {
  const token = useSearchParams().get("token") ?? "";
  const off = useMutation({ mutationFn: () => api.unsubscribe(token) });
  const started = useRef(false);
  useEffect(() => {
    if (token && !started.current) {
      started.current = true;
      off.mutate();
    }
  }, [token, off]);

  if (!token) return <FormError message="This link is incomplete. Turn reminders off in Settings." />;
  if (off.isError) return <FormError message={off.error.message} />;
  if (!off.isSuccess)
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
        <Spinner /> Turning off reminders…
      </p>
    );
  return (
    <div className="flex flex-col items-start gap-3" role="status">
      <span className="flex h-10 w-10 items-center justify-center rounded-md bg-primary-soft text-primary">
        <BellOff className="h-5 w-5" aria-hidden />
      </span>
      <h1 className="text-2xl font-semibold">Reminders are off</h1>
      <p className="text-muted-foreground">
        You won&apos;t get the 8 PM check-in email any more. You can turn it back on in Settings.
      </p>
    </div>
  );
}

export default function RemindersOffPage() {
  return (
    <div className="flex min-h-dvh flex-col px-5 py-8 sm:px-8">
      <Wordmark />
      <main className="flex flex-1 flex-col items-start justify-center gap-6 sm:mx-auto sm:w-full sm:max-w-md">
        <Suspense fallback={<Spinner />}>
          <TurnOff />
        </Suspense>
        <Button asChild variant="outline">
          <Link href="/settings">Open Settings</Link>
        </Button>
      </main>
    </div>
  );
}
