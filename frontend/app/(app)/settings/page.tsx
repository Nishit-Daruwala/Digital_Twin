"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useMe } from "@/lib/hooks";
import type { Consent, ConsentSource } from "@/lib/types";
import { PageHeader } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { FormError } from "@/components/ui/alert";
import { Spinner } from "@/components/spinner";

const CONSENT_LABELS: Record<ConsentSource, { title: string; desc: string }> = {
  checkin: { title: "Check-ins", desc: "Mood, energy, stress, focus and sleep." },
  activities: { title: "Activity log", desc: "Planned and completed tasks, time spent." },
  chat: { title: "Chat messages", desc: "What you tell your twin in chat." },
  decisions: { title: "Decisions", desc: "Decisions you log and their outcomes." },
};

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

  return (
    <>
      <PageHeader title="Settings" description="Your profile and what your twin may learn from." />

      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Profile</CardTitle>
          </CardHeader>
          <CardContent>
            {me && (
              <dl className="grid gap-3 text-sm sm:grid-cols-[140px_1fr]">
                <dt className="text-muted-foreground">Name</dt>
                <dd>{me.user.name}</dd>
                <dt className="text-muted-foreground">Email</dt>
                <dd className="break-all">{me.user.email}</dd>
                <dt className="text-muted-foreground">Role</dt>
                <dd>{me.user.role}</dd>
                <dt className="text-muted-foreground">Goals</dt>
                <dd>{me.profile.goals.join(", ")}</dd>
                <dt className="text-muted-foreground">Categories</dt>
                <dd>{me.profile.categories.join(", ")}</dd>
              </dl>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Data sources</CardTitle>
            <CardDescription>
              Turn a source off and your twin stops learning from it.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {consents.isLoading ? (
              <Spinner />
            ) : (
              <ul className="flex flex-col divide-y">
                {consents.data?.map((c) => (
                  <li key={c.source} className="flex items-center justify-between gap-4 py-3">
                    <div>
                      <p id={`consent-${c.source}`} className="text-sm font-medium">
                        {CONSENT_LABELS[c.source].title}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {CONSENT_LABELS[c.source].desc}
                      </p>
                    </div>
                    <Switch
                      aria-labelledby={`consent-${c.source}`}
                      checked={c.allowed}
                      onCheckedChange={(allowed) => toggle.mutate({ source: c.source, allowed })}
                    />
                  </li>
                ))}
              </ul>
            )}
            <FormError message={consents.error?.message ?? toggle.error?.message} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Account</CardTitle>
            <CardDescription>Data export and twin deletion arrive in a later phase.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" onClick={logout}>
              <LogOut /> Log out
            </Button>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
