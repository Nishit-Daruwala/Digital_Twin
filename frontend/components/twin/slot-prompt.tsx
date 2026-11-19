"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Clock, X } from "lucide-react";
import { api } from "@/lib/api";
import { qk } from "@/lib/hooks";
import { SLOT_QUESTION, isSkipped, setSkipped } from "@/lib/slots";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Scale } from "@/components/ui/scale";
import { FormError } from "@/components/ui/alert";
import { Spinner } from "@/components/spinner";

/**
 * "How's your afternoon?" Shown when the current part of the day has no check-in yet.
 * Optional by design: Skip hides it for this slot on this device, nothing else.
 * Before the day's full check-in it links to the check-in page; after it, it is a
 * two-tap quick check-in right here.
 */
export function SlotPrompt() {
  const qc = useQueryClient();
  const today = useQuery({ queryKey: qk.checkinToday, queryFn: api.checkinToday });
  const [, rerender] = useState(0);
  const [mood, setMood] = useState(3);
  const [energy, setEnergy] = useState(3);
  const save = useMutation({
    mutationFn: () => api.saveCheckin({ mood, energy, slot: today.data!.current_slot }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["checkins"] });
      qc.invalidateQueries({ queryKey: qk.dashboard });
    },
  });

  const t = today.data;
  if (!t) return null;
  const slot = t.current_slot;
  const done = t.slots.find((s) => s.slot === slot)?.checkin;
  if (done || isSkipped(t.date, slot)) return null;

  function skip() {
    setSkipped(t!.date, slot, true);
    rerender((n) => n + 1);
  }

  return (
    <Card className="animate-fade-up border-primary/25 p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary">
          <Clock className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{SLOT_QUESTION[slot]}</p>
          <p className="text-sm text-muted-foreground">
            {t.full_done
              ? "A quick check-in teaches your twin how your day usually goes. Optional."
              : "No check-in yet today. It takes about 20 seconds."}
          </p>
        </div>
        <button
          type="button"
          onClick={skip}
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          aria-label={`Skip this ${slot}`}
          title={`Skip this ${slot}`}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {t.full_done ? (
        <form
          className="mt-4 flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="grid gap-5 sm:grid-cols-2">
            <Scale label="Mood" low="Low" high="Great" value={mood} onChange={setMood} />
            <Scale label="Energy" low="Drained" high="Energised" value={energy} onChange={setEnergy} />
          </div>
          <FormError message={save.error?.message} />
          <div className="flex items-center gap-2">
            <Button type="submit" size="sm" disabled={save.isPending}>
              {save.isPending && <Spinner className="text-primary-foreground" />}
              Save
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={skip}>
              Skip
            </Button>
          </div>
        </form>
      ) : (
        <div className="mt-4 flex items-center gap-2">
          <Button asChild size="sm">
            <Link href="/checkin">
              Check in <ArrowRight />
            </Link>
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={skip}>
            Skip
          </Button>
        </div>
      )}
    </Card>
  );
}
