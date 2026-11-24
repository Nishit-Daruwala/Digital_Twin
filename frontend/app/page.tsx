"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { tokens } from "@/lib/api";
import { FullPageSpinner } from "@/components/spinner";

/** Entry point: logged-in users go to Chat (home), everyone else to login. */
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(tokens.get() ? "/checkin" : "/login");
  }, [router]);
  return <FullPageSpinner />;
}
