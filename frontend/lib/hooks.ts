"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export const qk = {
  me: ["me"] as const,
  checkins: (from?: string, to?: string) => ["checkins", from, to] as const,
  checkinToday: ["checkins", "today"] as const,
  activities: (from?: string, to?: string) => ["activities", from, to] as const,
  consents: ["consents"] as const,
  chat: ["chat"] as const,
  decisions: ["decisions"] as const,
  dashboard: ["dashboard"] as const,
  pending: ["predictions", "pending"] as const,
};

export function useMe(enabled = true) {
  return useQuery({ queryKey: qk.me, queryFn: api.me, enabled });
}
