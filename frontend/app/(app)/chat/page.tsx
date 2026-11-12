"use client";

import Link from "next/link";
import { MessageCircle } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";

export default function ChatPage() {
  return (
    <>
      <PageHeader title="Chat with your twin" />
      <EmptyState
        icon={MessageCircle}
        title="Your twin is still learning to talk"
        description="Chat arrives in Phase 2. For now, start with a daily check-in and log your activities so your twin has something to learn from."
        action={
          <div className="flex gap-2">
            <Button asChild>
              <Link href="/checkin">Do today&apos;s check-in</Link>
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
