"use client";

import Link from "next/link";
import { ArrowRight, MessageSquare } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { useMe } from "@/lib/hooks";

export default function ChatPage() {
  const { data: me } = useMe();
  const first = me?.user.name.split(" ")[0];
  return (
    <>
      <PageHeader eyebrow="Chat" title={first ? `Hello, ${first}` : "Hello"} />
      <EmptyState
        icon={MessageSquare}
        title="Your twin is still learning to talk"
        description="Chat arrives in the next phase. For now, start with a daily check-in and log your activities so your twin has something to learn from."
        action={
          <div className="flex flex-wrap gap-2">
            <Button asChild className="group">
              <Link href="/checkin">
                Do today&apos;s check-in
                <ArrowRight className="transition-transform duration-200 group-hover:translate-x-0.5" />
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/log">Log an activity</Link>
            </Button>
          </div>
        }
      />
    </>
  );
}
