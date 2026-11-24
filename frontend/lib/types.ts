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
  timezone: string | null; // IANA name; set from the browser on first load
  email_reminders: boolean; // 8 PM email on days without a check-in
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

export type Slot = "morning" | "afternoon" | "evening";

/** Full check-in (everything) or quick check-in (mood + energy only). Date and slot default
 *  to the user's current local day and part of the day. */
export interface CheckinIn {
  date?: string; // YYYY-MM-DD
  slot?: Slot;
  mood: number;
  energy: number;
  stress?: number | null;
  focus?: number | null;
  sleep_hours?: number | null;
  note?: string | null;
}

/** Saved check-in. Scores can be null for quick check-ins or chat cards with only some fields. */
export interface Checkin {
  id: string;
  date: string;
  slot: Slot;
  checked_at: string | null;
  mood: number | null;
  energy: number | null;
  stress: number | null;
  focus: number | null;
  sleep_hours: number | null;
  note: string | null;
  source: "manual" | "ai";
  updated_at: string;
}

export interface SlotState {
  slot: Slot;
  label: string;
  window: string;
  started: boolean;
  current: boolean;
  checkin: Checkin | null;
}

/** Today's three slots (GET /checkins/today). */
export interface CheckinDay {
  date: string;
  current_slot: Slot;
  timezone: string;
  full_done: boolean;
  slots: SlotState[];
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

// ---------- Phase 2: chat, extraction, decisions, demo ----------

export interface CardCheckin {
  mood: number | null;
  energy: number | null;
  stress: number | null;
  focus: number | null;
  sleep_hours: number | null;
  slot?: Slot | null;
}

export interface CardActivity {
  title: string;
  category: string;
  duration_min: number | null;
  planned: boolean;
  completed: boolean;
  start_time: string | null;
}

export interface CardDecision {
  text: string;
  options: string[];
  choice: string | null;
  reasoning: string | null;
}

export interface ExtractionCard {
  date: string;
  checkin: CardCheckin;
  activities: CardActivity[];
  decisions: CardDecision[];
}

export type ExtractionStatus = "pending" | "confirmed" | "dismissed";

export interface ChatMessage {
  id: string;
  role: "user" | "twin";
  text: string;
  created_at: string;
  learnable: boolean;
  extraction: ExtractionCard | null;
  extraction_status: ExtractionStatus | null;
}

export type ChatEvent =
  | { type: "user_message"; message: ChatMessage }
  | { type: "extraction"; message_id: string; card: ExtractionCard }
  | { type: "token"; text: string }
  | { type: "done"; message: ChatMessage }
  | { type: "error"; detail: string };

export interface Decision {
  id: string;
  text: string;
  options: string[];
  choice: string | null;
  reasoning: string | null;
  outcome_rating: number | null;
  source: "manual" | "ai";
  created_at: string;
}

export interface DecisionIn {
  text: string;
  options: string[];
  choice: string | null;
  reasoning: string | null;
}

export interface ConfirmResult {
  message: ChatMessage;
  checkin: Checkin | null;
  activities: Activity[];
  decisions: Decision[];
}

export type Persona = "student" | "developer" | "founder" | "noise";

export interface SeedResult {
  persona: Persona;
  days: number;
  checkins: number;
  activities: number;
  messages: number;
  decisions: number;
  planted_patterns: string[];
  pipeline: string;
}

// ---------- Phase 3: insights, predictions, dashboard ----------

export interface Insight {
  id: string;
  type: "pattern" | "anomaly" | "rhythm";
  key: string | null;
  text: string;
  evidence: Record<string, unknown> & {
    r?: number;
    p?: number;
    p_adj?: number;
    n?: number;
    lag?: number;
    feature?: string;
    target?: string;
    worse_mean?: number;
    other_mean?: number;
    n_worse?: number;
    n_other?: number;
    worse_side?: "high" | "low";
    threshold?: number;
    binary?: boolean;
    template?: string;
    wording?: "llm" | "template";
    fading?: boolean;
    kind?: string;
    metric?: string;
    worse?: boolean;
  };
  confidence: number | null;
  rank: number | null;
  first_seen: string | null;
  last_seen: string | null;
  is_new: boolean;
}

export interface Contributor {
  feature: string;
  label: string;
  value: number | null;
  impact: number;
  share: number;
  direction: "up" | "down";
}

export interface Prediction {
  id: string;
  for_date: string;
  target: "mood" | "energy" | "task";
  task_id: string | null;
  task_title: string | null;
  predicted: number;
  baseline: number | null;
  low: number | null;
  high: number | null;
  model_kind: string | null;
  backtest: boolean;
  actual: number | null;
  confirmed_at: string | null;
  explanation: {
    model?: string;
    contributors?: Contributor[];
    summary?: string | null;
    start_from?: number | null;
    units?: string;
    metrics?: Record<string, unknown>;
    time_of_day?: TimeOfDay;
  };
  suggested_actual: number | null;
}

/** Tomorrow by slot = the daily prediction + the person's usual offset for that slot. */
export interface TimeOfDay {
  learned: boolean;
  slots: Record<Slot, { value: number; offset: number; n: number }>;
}

export interface Accuracy {
  accuracy: number | null;
  baseline_accuracy: number | null;
  n: number;
  backtest_share: number;
  by_target: Record<string, number>;
  by_slot?: { accuracy: number | null; n: number };
}

export interface JobRun {
  id: string;
  trigger: string;
  status: "running" | "ok" | "error" | "skipped";
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  steps: Record<string, Record<string, unknown>>;
  error: string | null;
}

export interface SeriesPoint {
  date: string;
  mood: number | null;
  energy: number | null;
  focus: number | null;
  stress: number | null;
  sleep_hours: number | null;
}

export interface Dashboard {
  data_days: number;
  learning: { days: number; target: number; phase: "learning" | "predicting" };
  accuracy: Accuracy;
  tomorrow: Prediction[];
  insights: Insight[];
  anomalies: Insight[];
  rhythm: Insight[];
  traits: Record<string, Trait & { detail?: string }>;
  series: SeriesPoint[];
  minutes_by_category: { category: string; minutes: number }[];
  last_run: JobRun | null;
  pending_count: number;
}

// ---------- Phase 4: recommendations, what-if, privacy ----------

export interface Recommendation {
  id: string;
  for_date: string;
  type: string;
  text: string;
  reason: string | null;
  rank: number | null;
  feedback: 1 | -1 | null;
  created_at: string;
}

/** What the twin has learned about one kind of advice from your thumbs. */
export interface TypeLearning {
  type: string;
  label: string;
  likes: number;
  dislikes: number;
  preference: number; // 0..1, 0.5 = no opinion yet
}

export interface Recommendations {
  for_date: string | null;
  items: Recommendation[];
  learning: TypeLearning[];
  policy: string;
}

export interface WhatIfControl {
  key: string;
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
  value: number;
  source: string;
}

export interface WhatIfResult {
  value: number;
  baseline: number;
  delta: number;
  low: number;
  high: number;
  model_kind: string;
  learned: boolean;
  contributors: Contributor[];
  summary: string | null;
  time_of_day: TimeOfDay | null;
}

export interface WhatIf {
  controls: WhatIfControl[];
  results: Record<string, WhatIfResult>;
  applied: Record<string, number>;
  clipped: string[];
  note: string | null;
  ms: number;
}
