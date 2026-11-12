// Mirrors backend/app/schemas/*. Keep in sync with the Pydantic models.

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Trait {
  value: unknown;
  label: string;
  confidence: number;
  source: "quiz" | "data";
}

export interface TwinProfile {
  goals: string[];
  categories: string[];
  onboarding: { quiz?: QuizAnswers };
  traits: Record<string, Trait>;
  accuracy_score: number | null;
  data_days: number;
  updated_at: string;
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: string | null;
  created_at: string;
}

export interface Me {
  user: User;
  profile: TwinProfile;
  onboarded: boolean;
}

export interface QuizAnswers {
  best_time: "morning" | "afternoon" | "evening" | "night";
  plans_ahead: number; // 1-5
  estimate_bias: "faster" | "accurate" | "slower" | "much_slower";
  routine: number; // 1-5
  stress_source: "deadlines" | "people" | "sleep" | "uncertainty" | "workload";
}

export interface OnboardingIn {
  role: string;
  goals: string[];
  categories: string[];
  quiz: QuizAnswers;
}

export interface CheckinIn {
  date: string; // YYYY-MM-DD
  mood: number;
  energy: number;
  stress: number;
  focus: number;
  sleep_hours: number | null;
  note: string | null;
}

export interface Checkin extends CheckinIn {
  id: string;
  source: string;
  updated_at: string;
}

export interface ActivityIn {
  date: string;
  category: string;
  title: string;
  start_time?: string | null; // HH:MM
  duration_min?: number | null;
  planned_min?: number | null;
  planned: boolean;
  completed: boolean;
}

export interface Activity extends Required<ActivityIn> {
  id: string;
  source: string;
  created_at: string;
}

export type ConsentSource = "chat" | "checkin" | "activities" | "decisions";

export interface Consent {
  source: ConsentSource;
  allowed: boolean;
}
