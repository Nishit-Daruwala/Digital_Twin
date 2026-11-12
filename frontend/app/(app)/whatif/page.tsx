"use client";

import { FlaskConical } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";

export default function WhatIfPage() {
  return (
    <>
      <PageHeader eyebrow="Simulator" title="What if…" />
      <EmptyState
        icon={FlaskConical}
        title="Not ready yet"
        description="Once your twin has a model of you, you can change things like sleep or study time and see how tomorrow shifts."
      />
    </>
  );
}
