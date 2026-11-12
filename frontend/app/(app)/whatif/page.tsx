"use client";

import { FlaskConical } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";

export default function WhatIfPage() {
  return (
    <>
      <PageHeader title="What-if simulator" />
      <EmptyState
        icon={FlaskConical}
        title="Not ready yet"
        description="Once your twin has a model of you (Phase 4), you can move sliders like sleep or study time and see how tomorrow changes."
      />
    </>
  );
}
