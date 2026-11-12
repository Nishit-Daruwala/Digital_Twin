"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FlaskConical,
  LayoutDashboard,
  ListChecks,
  MessageCircle,
  Settings,
  SmilePlus,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Me } from "@/lib/types";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/chat", label: "Chat", icon: MessageCircle },
  { href: "/checkin", label: "Check-in", icon: SmilePlus },
  { href: "/log", label: "Log", icon: ListChecks },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/whatif", label: "What-if", icon: FlaskConical },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ me, children }: { me: Me; children: React.ReactNode }) {
  const pathname = usePathname();
  const active = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <div className="min-h-dvh md:flex">
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r bg-card md:flex">
        <div className="flex items-center gap-2 px-5 py-5">
          <Logo />
          <span className="text-lg font-semibold">Twin</span>
        </div>
        <nav aria-label="Main" className="flex flex-1 flex-col gap-1 px-3">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={active(href) ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active(href)
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" aria-hidden />
              {label}
            </Link>
          ))}
        </nav>
        <div className="border-t px-5 py-4 text-sm">
          <p className="truncate font-medium">{me.user.name}</p>
          <p className="truncate text-muted-foreground">{me.user.role}</p>
        </div>
      </aside>

      {/* Mobile header */}
      <header className="sticky top-0 z-10 flex items-center gap-2 border-b bg-background/90 px-4 py-3 backdrop-blur md:hidden">
        <Logo />
        <span className="font-semibold">Twin</span>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 pb-24 pt-6 md:px-8 md:pb-10">
        {children}
      </main>

      {/* Mobile bottom nav */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-10 grid grid-cols-6 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
      >
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={active(href) ? "page" : undefined}
            className={cn(
              "flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium",
              active(href) ? "text-primary" : "text-muted-foreground",
            )}
          >
            <Icon className="h-5 w-5" aria-hidden />
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

export function Logo({ className }: { className?: string }) {
  // Two overlapping circles: you and your twin.
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("h-7 w-7", className)}>
      <circle cx="12" cy="16" r="9" className="fill-primary/80" />
      <circle cx="20" cy="16" r="9" className="fill-primary/40" />
    </svg>
  );
}

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
    </div>
  );
}
