"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useMe } from "@/lib/hooks";
import type { Consent, ConsentSource } from "@/lib/types";
import { PageHeader } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { FormError } from "@/components/ui/alert";
import { Skeleton } from "@/components/spinner";

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

      <Section
        title="Session"
        description="Data export and twin deletion arrive in a later phase."
      >
        <Button variant="outline" onClick={logout}>
          <LogOut /> Log out
        </Button>
      </Section>
    </>
  );
}
