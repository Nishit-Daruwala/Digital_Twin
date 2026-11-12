// Typed API client. Attaches the access token, refreshes it once on 401,
// and signs the user out if the refresh token is also invalid.
import type {
  Activity,
  ActivityIn,
  Checkin,
  CheckinIn,
  Consent,
  ConsentSource,
  Me,
  OnboardingIn,
  TokenPair,
  TwinProfile,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const STORAGE_KEY = "twin.tokens";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// ---------- token storage ----------

type Tokens = { access_token: string; refresh_token: string };

export const tokens = {
  get(): Tokens | null {
    if (typeof window === "undefined") return null;
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as Tokens) : null;
    } catch {
      return null;
    }
  },
  set(t: Tokens) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(t));
    } catch {
      /* storage unavailable: session lasts until reload */
    }
  },
  clear() {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  },
};

// ---------- core request ----------

function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    // FastAPI validation error: [{loc, msg}]
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = d.loc?.filter((p) => p !== "body").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return `Request failed (${status})`;
}

let refreshing: Promise<boolean> | null = null;

async function refreshAccess(): Promise<boolean> {
  const t = tokens.get();
  if (!t) return false;
  refreshing ??= fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: t.refresh_token }),
  })
    .then(async (r) => {
      if (!r.ok) return false;
      const { access_token } = await r.json();
      tokens.set({ ...t, access_token });
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

function signOutAndRedirect() {
  tokens.clear();
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const t = tokens.get();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (t) headers.set("Authorization", `Bearer ${t.access_token}`);

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the Twin server. Is the backend running?");
  }

  if (res.status === 401 && t && retry) {
    if (await refreshAccess()) return request<T>(path, init, false);
    signOutAndRedirect();
  }
  if (res.status === 204) return undefined as T;

  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, errorMessage(body, res.status));
  return body as T;
}

const json = (method: string, data: unknown): RequestInit => ({
  method,
  body: JSON.stringify(data),
});

function qs(params: Record<string, string | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
}

// ---------- endpoints ----------

export const api = {
  async register(email: string, password: string, name: string) {
    const t = await request<TokenPair>("/auth/register", json("POST", { email, password, name }));
    tokens.set(t);
  },
  async login(email: string, password: string) {
    const t = await request<TokenPair>("/auth/login", json("POST", { email, password }));
    tokens.set(t);
  },
  logout() {
    tokens.clear();
  },

  me: () => request<Me>("/me"),
  onboarding: (body: OnboardingIn) => request<TwinProfile>("/onboarding", json("POST", body)),

  saveCheckin: (body: CheckinIn) => request<Checkin>("/checkins", json("POST", body)),
  checkins: (from?: string, to?: string) => request<Checkin[]>(`/checkins${qs({ from, to })}`),

  createActivity: (body: ActivityIn) => request<Activity>("/activities", json("POST", body)),
  activities: (from?: string, to?: string) =>
    request<Activity[]>(`/activities${qs({ from, to })}`),
  updateActivity: (id: string, body: { completed?: boolean; duration_min?: number | null }) =>
    request<Activity>(`/activities/${id}`, json("PATCH", body)),
  deleteActivity: (id: string) => request<void>(`/activities/${id}`, { method: "DELETE" }),

  consents: () => request<Consent[]>("/privacy/consents"),
  setConsent: (source: ConsentSource, allowed: boolean) =>
    request<Consent[]>("/privacy/consents", json("PUT", { source, allowed })),
};
