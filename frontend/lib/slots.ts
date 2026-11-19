import type { Checkin, Slot } from "./types";

export const SLOTS: Slot[] = ["morning", "afternoon", "evening"];

export const SLOT_LABEL: Record<Slot, string> = {
  morning: "Morning",
  afternoon: "Afternoon",
  evening: "Evening",
};

export const SLOT_WINDOW: Record<Slot, string> = {
  morning: "until 12:00",
  afternoon: "12:00–17:00",
  evening: "after 17:00",
};

export const SLOT_QUESTION: Record<Slot, string> = {
  morning: "How's your morning?",
  afternoon: "How's your afternoon?",
  evening: "How's your evening?",
};

/** A full check-in has the once-a-day questions (sleep, stress, focus). */
export function isFull(c: Checkin | null | undefined): boolean {
  return !!c && (c.sleep_hours != null || c.stress != null || c.focus != null);
}

/** Local (day, slot) of a moment; 00:00–03:59 is still the previous day's evening. */
function slotOfMoment(d: Date): { day: string; slot: Slot } {
  const h = d.getHours();
  const local = new Date(d.getTime() - (h < 4 ? 864e5 : 0));
  const day = `${local.getFullYear()}-${String(local.getMonth() + 1).padStart(2, "0")}-${String(local.getDate()).padStart(2, "0")}`;
  return { day, slot: h < 4 || h >= 17 ? "evening" : h < 12 ? "morning" : "afternoon" };
}

/** When it was saved, e.g. "09:12". A slot filled in afterwards (the morning, saved at
 *  9 PM) says "added later" rather than showing an evening time under "Morning". */
export function timeOf(c: Checkin): string | null {
  if (!c.checked_at) return null;
  const at = new Date(c.checked_at);
  const when = slotOfMoment(at);
  if (when.day !== c.date || when.slot !== c.slot) return "added later";
  // 24-hour: short enough for the narrow slot tiles on phones
  return at.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
}

// Skipping a slot only hides the prompt on this device; it is never stored or held against
// the user. Storage can be unavailable (private mode), so every access is guarded.
const skipKey = (date: string, slot: Slot) => `twin.skip.${date}.${slot}`;

export function isSkipped(date: string, slot: Slot): boolean {
  try {
    return window.localStorage.getItem(skipKey(date, slot)) === "1";
  } catch {
    return false;
  }
}

export function setSkipped(date: string, slot: Slot, skipped: boolean): void {
  try {
    if (skipped) window.localStorage.setItem(skipKey(date, slot), "1");
    else window.localStorage.removeItem(skipKey(date, slot));
  } catch {
    /* ignore */
  }
}
