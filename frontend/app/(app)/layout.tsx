"use client";

import { AuthGuard } from "@/components/auth-guard";
import { AppShell } from "@/components/app-shell";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AuthGuard need="onboarded">{(me) => <AppShell me={me}>{children}</AppShell>}</AuthGuard>;
}
