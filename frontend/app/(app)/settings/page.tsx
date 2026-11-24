"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bell, Check, Database, Download, LogOut, Mail, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useMe } from "@/lib/hooks";
import type { Consent, ConsentSource, Me, Persona } from "@/lib/types";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { FormError } from "@/components/ui/alert";
import { Skeleton, Spinner } from "@/components/spinner";

const CONSENT_LABELS: Record<ConsentSource, { title: string; desc: string }> = {
  checkin: { title: "Check-ins", desc: "Mood, energy, stress, focus and sleep." },
  activities: { title: "Activity log", desc: "Planned and completed tasks, time spent." },
  chat: { title: "Chat messages", desc: "What you tell your twin in chat." },
  decisions: { title: "Decisions", desc: "Decisions you log and their outcomes." },
};

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-4 border-b py-8 first:pt-0 last:border-0 md:grid-cols-[240px_1fr] md:gap-10">
      <div>
        <h2 className="text-[15px] font-semibold">{title}</h2>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{description}</p>
      </div>
      <div>{children}</div>
    </section>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: me } = useMe();

  const consents = useQuery({ queryKey: qk.consents, queryFn: api.consents });
  const toggle = useMutation({
    mutationFn: ({ source, allowed }: Consent) => api.setConsent(source, allowed),
    onMutate: async ({ source, allowed }) => {
      await qc.cancelQueries({ queryKey: qk.consents });
      const prev = qc.getQueryData<Consent[]>(qk.consents);
      qc.setQueryData<Consent[]>(qk.consents, (old) =>
        old?.map((c) => (c.source === source ? { ...c, allowed } : c)),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(qk.consents, ctx.prev),
    onSuccess: (data) => qc.setQueryData(qk.consents, data),
  });

  function logout() {
    api.logout();
    qc.clear();
    router.replace("/login");
  }

  const profileRows = me
    ? [
        { k: "Name", v: me.user.name },
        { k: "Email", v: me.user.email },
        { k: "Role", v: me.user.role ?? "—" },
        { k: "Goals", v: me.profile.goals.join(", ") },
        { k: "Categories", v: me.profile.categories.join(", ") },
      ]
    : [];

  return (
    <>
      <PageHeader eyebrow="Account" title="Settings" />

      <Section title="Profile" description="Set during onboarding.">
        <Card>
          {me ? (
            <dl className="divide-y">
              {profileRows.map((r) => (
                <div key={r.k} className="grid gap-1 px-5 py-3.5 text-sm sm:grid-cols-[120px_1fr]">
                  <dt className="text-muted-foreground">{r.k}</dt>
                  <dd className="break-words font-medium">{r.v}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <div className="flex flex-col gap-3 p-5">
              <Skeleton className="h-5" />
              <Skeleton className="h-5" />
            </div>
          )}
        </Card>
      </Section>

      <Section
        title="Timezone"
        description="Check-in slots (morning, afternoon, evening) and the 8 PM reminder follow your local time."
      >
        <TimezoneSetting current={me?.user.timezone ?? null} />
      </Section>

      <Section
        title="Reminders"
        description="One email at 8 PM your time, only on days you haven't checked in. A single check-in is enough to skip it."
      >
        {me ? (
          <ReminderSetting enabled={me.user.email_reminders} email={me.user.email} timezone={me.user.timezone} />
        ) : (
          <Skeleton className="h-24" />
        )}
      </Section>

      <Section
        title="Data sources"
        description="Switch a source off and your twin stops learning from it."
      >
        <Card>
          {consents.isLoading ? (
            <div className="flex flex-col gap-3 p-5">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : (
            <ul className="divide-y">
              {consents.data?.map((c) => (
                <li key={c.source} className="flex items-center justify-between gap-4 px-5 py-4">
                  <div>
                    <p id={`consent-${c.source}`} className="text-sm font-semibold">
                      {CONSENT_LABELS[c.source].title}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {CONSENT_LABELS[c.source].desc}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="hidden w-14 text-right font-mono text-[11px] uppercase text-muted-foreground sm:inline">
                      {c.allowed ? "On" : "Off"}
                    </span>
                    <Switch
                      aria-labelledby={`consent-${c.source}`}
                      checked={c.allowed}
                      onCheckedChange={(allowed) => toggle.mutate({ source: c.source, allowed })}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <FormError message={consents.error?.message ?? toggle.error?.message} className="mt-3" />
      </Section>

      <YourData email={me?.user.email ?? ""} />

      <DemoData />

      <Section title="Session" description="Log out on this device.">
        <Button variant="outline" onClick={logout}>
          <LogOut /> Log out
        </Button>
      </Section>
    </>
  );
}

const PERSONAS: { key: Persona; title: string; desc: string }[] = [
  { key: "student", title: "Student", desc: "Night owl. Short sleep hurts next-day focus; tasks take 1.6× the estimate." },
  { key: "developer", title: "Developer", desc: "Morning person. Busy meeting days drain energy; Mondays are low." },
  { key: "founder", title: "Founder", desc: "Stress builds two days before mood drops; exercise lifts the next day." },
  { key: "noise", title: "Control (random)", desc: "No hidden patterns at all. A good twin should find nothing." },
];

function YourData({ email }: { email: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState("");
  const exp = useMutation({
    mutationFn: api.exportData,
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `twin-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },
  });
  const del = useMutation({
    mutationFn: () => api.deleteMe(confirm),
    onSuccess: () => {
      api.logout();
      qc.clear();
      router.replace("/login");
    },
  });
  const matches = !!email && confirm.trim().toLowerCase() === email.toLowerCase();
  return (
    <Section
      title="Your data"
      description="Download everything Twin stores about you, or delete your twin for good."
    >
      <Card className="flex flex-col divide-y">
        <div className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium">Export</p>
            <p className="text-sm text-muted-foreground">
              Check-ins, activities, chat, decisions, insights, predictions and suggestions, as
              one JSON file.
            </p>
          </div>
          <Button variant="outline" onClick={() => exp.mutate()} disabled={exp.isPending}>
            {exp.isPending ? <Spinner /> : <Download />} Download my data
          </Button>
        </div>
        <div className="flex flex-col gap-3 p-5">
          <div>
            <p className="text-sm font-medium text-destructive">Delete my twin</p>
            <p className="text-sm text-muted-foreground">
              Permanently removes your account, all your data and your twin&apos;s models. This
              can&apos;t be undone. Type your email to confirm.
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              aria-label="Type your email to confirm"
              placeholder={email}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="off"
            />
            <Button
              variant="destructive"
              onClick={() => del.mutate()}
              disabled={!matches || del.isPending}
            >
              {del.isPending ? <Spinner className="text-destructive-foreground" /> : <Trash2 />}
              Delete everything
            </Button>
          </div>
        </div>
      </Card>
      <FormError message={exp.error?.message ?? del.error?.message} className="mt-3" />
    </Section>
  );
}

function ReminderSetting({
  enabled,
  email,
  timezone,
}: {
  enabled: boolean;
  email: string;
  timezone: string | null;
}) {
  const qc = useQueryClient();
  const set = useMutation({
    mutationFn: (email_reminders: boolean) => api.updateMe({ email_reminders }),
    onMutate: (email_reminders) => {
      const prev = qc.getQueryData<Me>(qk.me);
      qc.setQueryData<Me>(qk.me, (m) => (m ? { ...m, user: { ...m.user, email_reminders } } : m));
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(qk.me, ctx.prev),
    onSuccess: (m) => qc.setQueryData(qk.me, m),
  });
  const test = useMutation({ mutationFn: api.testReminder });
  return (
    <Card>
      <div className="flex items-center justify-between gap-4 px-5 py-4">
        <div className="flex items-start gap-3">
          <Bell className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <div>
            <p id="reminder-label" className="text-sm font-semibold">
              Check-in reminder email
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Sent to {email} at 8 PM ({(timezone ?? "UTC").replace(/_/g, " ")}).
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden w-14 text-right font-mono text-[11px] uppercase text-muted-foreground sm:inline">
            {enabled ? "On" : "Off"}
          </span>
          <Switch
            aria-labelledby="reminder-label"
            checked={enabled}
            disabled={set.isPending}
            onCheckedChange={(v) => set.mutate(v)}
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t px-5 py-3">
        <Button variant="outline" size="sm" onClick={() => test.mutate()} disabled={test.isPending}>
          {test.isPending ? <Spinner /> : <Mail />} Send me a test email
        </Button>
        {test.isSuccess && (
          <span className="flex items-center gap-1 text-sm text-success" role="status">
            <Check className="h-4 w-4" aria-hidden />
            {test.data.provider === "smtp"
              ? `Sent to ${test.data.sent_to}`
              : "Email sending isn't set up on the server, so it was written to the server log"}
          </span>
        )}
      </div>
      <FormError message={set.error?.message ?? test.error?.message} className="mx-5 mb-4" />
    </Card>
  );
}

function TimezoneSetting({ current }: { current: string | null }) {
  const qc = useQueryClient();
  const device = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  const options = Array.from(new Set([current, device, ...zones].filter(Boolean) as string[]));
  const set = useMutation({
    mutationFn: (timezone: string) => api.updateMe({ timezone }),
    onSuccess: (m) => {
      qc.setQueryData(qk.me, m);
      qc.invalidateQueries({ queryKey: ["checkins"] });
    },
  });
  return (
    <Card className="flex flex-col gap-3 p-5">
      <label htmlFor="tz" className="text-sm font-medium">
        Your timezone
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <select
          id="tz"
          className="h-10 min-w-0 max-w-full flex-1 rounded-md border border-input bg-card px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={current ?? ""}
          onChange={(e) => e.target.value && set.mutate(e.target.value)}
          disabled={set.isPending}
        >
          {!current && <option value="">Not set (using UTC)</option>}
          {options.map((z) => (
            <option key={z} value={z}>
              {z.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        {current !== device && (
          <Button variant="outline" size="sm" onClick={() => set.mutate(device)} disabled={set.isPending}>
            Use this device ({device.replace(/_/g, " ")})
          </Button>
        )}
        {set.isSuccess && (
          <span className="flex items-center gap-1 text-sm text-success" role="status">
            <Check className="h-4 w-4" aria-hidden /> Saved
          </span>
        )}
      </div>
      <FormError message={set.error?.message} />
    </Card>
  );
}

function DemoData() {
  const qc = useQueryClient();
  const [persona, setPersona] = useState<Persona>("student");
  const [days, setDays] = useState(60);
  const [armed, setArmed] = useState(false);

  const seed = useMutation({
    mutationFn: () => api.demoSeed(persona, days),
    onSuccess: () => {
      setArmed(false);
      // Everything changed: drop all cached data so every page refetches.
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      qc.invalidateQueries({ queryKey: qk.me });
    },
  });

  return (
    <Section
      title="Demo data"
      description="Fill your account with a synthetic person's history to see the twin with weeks of data."
    >
      <Card>
        <div className="flex flex-col gap-5 p-5">
          <div role="radiogroup" aria-label="Persona" className="grid gap-2 sm:grid-cols-2">
            {PERSONAS.map((p) => (
              <button
                key={p.key}
                type="button"
                role="radio"
                aria-checked={persona === p.key}
                onClick={() => {
                  setPersona(p.key);
                  setArmed(false);
                }}
                className={cn(
                  "rounded-md border p-3.5 text-left transition-[border-color,background-color] duration-150",
                  persona === p.key ? "border-primary bg-primary-soft" : "hover:border-foreground/35",
                )}
              >
                <p className={cn("text-sm font-semibold", persona === p.key && "text-primary")}>
                  {p.title}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{p.desc}</p>
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <span className="text-[13px] font-semibold" id="days-label">History</span>
            <div role="radiogroup" aria-labelledby="days-label" className="flex gap-1 rounded-md border bg-secondary p-1">
              {[30, 60, 90].map((d) => (
                <button
                  key={d}
                  type="button"
                  role="radio"
                  aria-checked={days === d}
                  onClick={() => {
                    setDays(d);
                    setArmed(false);
                  }}
                  className={cn(
                    "rounded-[5px] px-3 py-1 font-mono text-xs font-medium transition-colors",
                    days === d ? "bg-card shadow-card" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {d} days
                </button>
              ))}
            </div>
          </div>

          {seed.data && !seed.isPending && (
            <p role="status" className="flex animate-fade-in items-start gap-2 rounded-md border border-success/25 bg-success/[0.06] px-3 py-2.5 text-sm">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" strokeWidth={3} />
              Loaded {seed.data.checkins} check-ins, {seed.data.activities} activities,{" "}
              {seed.data.messages} chat messages and {seed.data.decisions} decisions, then updated
              your twin ({seed.data.pipeline}). See the Dashboard.
            </p>
          )}
          <FormError message={seed.error?.message} />
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t bg-secondary/40 px-5 py-4">
          {!armed ? (
            <Button variant="outline" onClick={() => setArmed(true)} disabled={seed.isPending}>
              <Database /> Load demo data
            </Button>
          ) : (
            <div className="flex animate-fade-in flex-wrap items-center gap-3">
              <span className="flex items-center gap-1.5 text-sm font-medium text-destructive">
                <AlertTriangle className="h-4 w-4" /> This replaces all your check-ins, activities, chat and decisions.
              </span>
              <Button variant="destructive" size="sm" onClick={() => seed.mutate()} disabled={seed.isPending}>
                {seed.isPending && <Spinner className="text-destructive-foreground" />}
                Replace my data
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setArmed(false)} disabled={seed.isPending}>
                Cancel
              </Button>
            </div>
          )}
        </div>
      </Card>
    </Section>
  );
}
