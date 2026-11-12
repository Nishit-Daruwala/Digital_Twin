"use client";

import { LayoutDashboard } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMe } from "@/lib/hooks";

export default function DashboardPage() {
  const { data: me } = useMe();
  const traits = me ? Object.entries(me.profile.traits) : [];

  return (
    <>
      <PageHeader title="Dashboard" />
      <div className="flex flex-col gap-6">
        <EmptyState
          icon={LayoutDashboard}
          title="Insights and predictions are on their way"
          description="Your twin needs a few days of check-ins first. Patterns, predictions and charts arrive in Phase 3."
        />
        {traits.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">First impression (from your quiz)</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="flex flex-wrap gap-2">
                {traits
                  .filter(([, t]) => t.label !== "not enough data yet")
                  .map(([key, t]) => (
                    <li key={key} className="rounded-full bg-secondary px-3 py-1 text-sm">
                      {t.label}
                    </li>
                  ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
