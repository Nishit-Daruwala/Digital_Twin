"use client";

import { useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FlaskConical,
  LayoutGrid,
  ListChecks,
  MessageSquare,
  Settings,
  Signpost,
  SunMedium,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Me } from "@/lib/types";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutGrid },
  { href: "/checkin", label: "Check-in", icon: SunMedium },
  { href: "/log", label: "Log", icon: ListChecks },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/decisions", label: "Decisions", icon: Signpost },
  { href: "/whatif", label: "What-if", icon: FlaskConical },
  { href: "/settings", label: "Settings", icon: Settings },
];

function initials(name: string) {
  return name
    .replace(/[^A-Za-zÀ-ɏ\s]/g, " ") // letters only: "Lin (founder)" -> "LF"
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

export function AppShell({ me, children }: { me: Me; children: React.ReactNode }) {
  const pathname = usePathname();
  const active = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  const page = NAV.find((n) => active(n.href));
  useEffect(() => {
    document.title = page ? `${page.label} · Twin` : "Twin";
  }, [page]);

  return (
    <div className="min-h-dvh md:flex">
      <a
        href="#main"
        className="fixed left-3 top-3 z-50 -translate-y-16 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-card transition-transform focus:translate-y-0"
      >
        Skip to content
      </a>
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col border-r bg-card md:flex">
        <div className="px-6 pb-6 pt-7">
          <HomeLink />
        </div>
        <nav aria-label="Main" className="flex flex-1 flex-col gap-0.5 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const on = active(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={on ? "page" : undefined}
                className={cn(
                  "group relative flex h-10 items-center gap-3 rounded-md px-3 text-sm transition-colors duration-150",
                  on
                    ? "bg-secondary font-semibold text-foreground"
                    : "font-medium text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    "absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-primary transition-all duration-200 ease-out",
                    on ? "opacity-100" : "scale-y-0 opacity-0",
                  )}
                />
                <Icon
                  className={cn(
                    "h-[18px] w-[18px] transition-colors",
                    on ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                  )}
                  strokeWidth={on ? 2.2 : 1.8}
                  aria-hidden
                />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="m-3 flex items-center gap-3 rounded-md border bg-background px-3 py-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary-soft font-mono text-xs font-medium text-primary">
            {initials(me.user.name)}
          </div>
          <div className="min-w-0 text-sm">
            <p className="truncate font-semibold leading-tight">{me.user.name}</p>
            <p className="truncate text-xs text-muted-foreground">{me.user.role}</p>
          </div>
        </div>
      </aside>

      {/* Mobile header */}
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b bg-card/95 px-4 backdrop-blur md:hidden">
        <HomeLink />
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary-soft font-mono text-[11px] font-medium text-primary">
          {initials(me.user.name)}
        </div>
      </header>

      <main id="main" tabIndex={-1} className="mx-auto outline-none w-full max-w-5xl flex-1 px-4 pb-28 pt-7 md:px-10 md:pb-12 md:pt-10">
        {/* Keyed by route so every page fades in on navigation */}
        <div key={pathname} className="animate-fade-up">
          {children}
        </div>
      </main>

      {/* Mobile bottom nav */}
      <nav
        aria-label="Main (mobile)"
        className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-7 border-t bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
      >
        {NAV.map(({ href, label, icon: Icon }) => {
          const on = active(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={on ? "page" : undefined}
              className={cn(
                "relative flex min-w-0 flex-col items-center gap-1 pb-2 pt-2.5 text-[10px] font-medium tracking-tight transition-colors",
                on ? "text-primary" : "text-muted-foreground",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "absolute inset-x-4 top-0 h-[2px] rounded-b-full bg-primary transition-all duration-200 ease-out",
                  on ? "opacity-100" : "scale-x-0 opacity-0",
                )}
              />
              <Icon className="h-5 w-5" strokeWidth={on ? 2.2 : 1.8} aria-hidden />
              <span className="max-w-full truncate px-0.5">{label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

/** Brand mark (icon only): you and your twin. Used where the full logo would be too small. */
export function Logo({ className }: { className?: string }) {
  return (
    <Image
      src="/twin-mark.png"
      alt=""
      aria-hidden
      width={178}
      height={128}
      className={cn("h-8 w-8 shrink-0 object-contain", className)}
    />
  );
}

/** The wordmark as a link home (the Dashboard). */
function HomeLink() {
  return (
    <Link
      href="/dashboard"
      aria-label="Twin, go to Dashboard"
      className="inline-flex rounded-md transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      <Wordmark />
    </Link>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <Image
      src="/twin-logo.png"
      alt="Twin"
      width={434}
      height={128}
      priority
      // self-start: in a column flexbox the image would otherwise stretch to full width
      className={cn("h-8 w-auto shrink-0 self-start object-contain", className)}
    />
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && <p className="eyebrow mb-2 text-primary">{eyebrow}</p>}
        <h1 className="text-[28px] font-semibold leading-tight md:text-[32px]">{title}</h1>
        {description && (
          <p className="mt-2 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {action}
    </div>
  );
}
