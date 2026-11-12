"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { tokens } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Me } from "@/lib/types";
import { FullPageSpinner } from "./spinner";
import { FormError } from "./ui/alert";

/**
 * Client-side gate. `need="onboarded"` for app pages, `need="new"` for the onboarding flow.
 * (Real access control is the backend: every route checks the JWT.)
 */
export function AuthGuard({
  need,
  children,
}: {
  need: "onboarded" | "new";
  children: (me: Me) => React.ReactNode;
}) {
  const router = useRouter();
  const [hasToken, setHasToken] = useState<boolean | null>(null);

  useEffect(() => {
    const ok = !!tokens.get();
    setHasToken(ok);
    if (!ok) router.replace("/login");
  }, [router]);

  const { data: me, error } = useMe(hasToken === true);

  // For the onboarding flow, decide only on first load: once the wizard finishes it
  // navigates itself, and the guard must not race it with a redirect of its own.
  const newUserAtLoad = useRef<boolean | null>(null);
  if (me && newUserAtLoad.current === null) newUserAtLoad.current = !me.onboarded;

  useEffect(() => {
    if (!me) return;
    if (need === "onboarded" && !me.onboarded) router.replace("/onboarding");
    if (need === "new" && newUserAtLoad.current === false) router.replace("/chat");
  }, [me, need, router]);

  if (error) {
    return (
      <div className="mx-auto max-w-md p-6">
        <FormError message={error.message} />
      </div>
    );
  }
  if (
    !me ||
    (need === "onboarded" && !me.onboarded) ||
    (need === "new" && newUserAtLoad.current === false)
  ) {
    return <FullPageSpinner />;
  }
  return <>{children(me)}</>;
}
