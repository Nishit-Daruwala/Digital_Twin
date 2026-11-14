/**
 * Chart colours (validated with the dataviz skill's validator on the white card surface:
 * CVD ΔE 27.0, normal-vision ΔE 33.1, both ≥ 3:1 contrast). Text never uses these.
 *   series-1 / "lowers": brand tangerine  ·  series-2 / "raises": blue
 */
export const VIZ = {
  mood: "#d54810",
  energy: "#2a78d6",
  sleep: "#2a78d6",
  minutes: "#d54810",
  up: "#2a78d6",
  down: "#d54810",
  grid: "#ebe9e4",
  axis: "#898781",
  baseline: "#c3c2b7",
} as const;

export const TARGET_LABEL: Record<string, string> = {
  mood: "Mood",
  energy: "Energy",
  task: "Task",
  focus: "Focus",
  completion_rate: "Task completion",
};

export const MODEL_LABEL: Record<string, string> = {
  mean: "2-week average",
  mean7: "7-day average",
  mean28: "4-week average",
  ridge: "Linear model",
  xgboost: "Tree model (XGBoost)",
  rate: "Your completion rate",
  logistic: "Linear model",
};

export function shortDate(d: string) {
  return new Date(`${d}T00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function relativeTime(iso: string | null | undefined) {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}
