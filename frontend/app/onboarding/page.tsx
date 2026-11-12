"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Plus, X } from "lucide-react";
import { api } from "@/lib/api";
import { qk } from "@/lib/hooks";
import type { QuizAnswers } from "@/lib/types";
import { AuthGuard } from "@/components/auth-guard";
import { Wordmark } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormError } from "@/components/ui/alert";
import { Spinner } from "@/components/spinner";
import { cn } from "@/lib/utils";

const ROLES = ["Student", "Developer", "Founder", "Designer", "Researcher", "Teacher"];

const CATEGORY_SUGGESTIONS: Record<string, string[]> = {
  student: ["Study", "Lectures", "Assignments", "Exercise", "Social", "Leisure"],
  developer: ["Deep work", "Meetings", "Code review", "Learning", "Exercise", "Leisure"],
  founder: ["Strategy", "Meetings", "Sales", "Hiring", "Exercise", "Family"],
  default: ["Work", "Meetings", "Learning", "Exercise", "Social", "Leisure", "Chores"],
};

const GOAL_SUGGESTIONS = [
  "Sleep 7+ hours",
  "Exercise 3x a week",
  "More deep work",
  "Less stress",
  "Finish tasks on time",
  "Consistent routine",
];

const MAX_GOALS = 5;
const MAX_CATEGORIES = 12;

type Question<K extends keyof QuizAnswers> = {
  key: K;
  text: string;
  options: { value: QuizAnswers[K]; label: string }[];
};

const QUIZ: [
  Question<"best_time">,
  Question<"plans_ahead">,
  Question<"estimate_bias">,
  Question<"routine">,
  Question<"stress_source">,
] = [
  {
    key: "best_time",
    text: "When do you usually do your best work?",
    options: [
      { value: "morning", label: "Morning" },
      { value: "afternoon", label: "Afternoon" },
      { value: "evening", label: "Evening" },
      { value: "night", label: "Late night" },
    ],
  },
  {
    key: "plans_ahead",
    text: "How much do you plan your day in advance?",
    options: [
      { value: 1, label: "Not at all" },
      { value: 2, label: "A little" },
      { value: 3, label: "Somewhat" },
      { value: 4, label: "Mostly" },
      { value: 5, label: "Every hour" },
    ],
  },
  {
    key: "estimate_bias",
    text: "Compared with your estimate, tasks usually take…",
    options: [
      { value: "faster", label: "Less time" },
      { value: "accurate", label: "About right" },
      { value: "slower", label: "A bit longer" },
      { value: "much_slower", label: "Much longer" },
    ],
  },
  {
    key: "routine",
    text: "How similar are your days to each other?",
    options: [
      { value: 1, label: "Every day differs" },
      { value: 2, label: "Mostly different" },
      { value: 3, label: "Mixed" },
      { value: 4, label: "Mostly the same" },
      { value: 5, label: "Same routine" },
    ],
  },
  {
    key: "stress_source",
    text: "What stresses you most often?",
    options: [
      { value: "deadlines", label: "Deadlines" },
      { value: "workload", label: "Workload" },
      { value: "people", label: "People" },
      { value: "sleep", label: "Poor sleep" },
      { value: "uncertainty", label: "Uncertainty" },
    ],
  },
];

const STEPS = ["Role", "Goals", "Categories", "Quick quiz"];

export default function OnboardingPage() {
  return <AuthGuard need="new">{(me) => <Wizard name={me.user.name} />}</AuthGuard>;
}

function Wizard({ name }: { name: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [dir, setDir] = useState<"fwd" | "back">("fwd");
  const [role, setRole] = useState("");
  const [goals, setGoals] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [quiz, setQuiz] = useState<Partial<QuizAnswers>>({});

  const save = useMutation({
    mutationFn: () =>
      api.onboarding({ role: role.trim(), goals, categories, quiz: quiz as QuizAnswers }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.me });
      router.replace("/checkin");
    },
  });

  const answered = QUIZ.filter((q) => quiz[q.key] !== undefined).length;
  const canNext = [
    role.trim().length > 0,
    goals.length > 0,
    categories.length > 0,
    answered === QUIZ.length,
  ][step];

  function go(to: number) {
    setDir(to > step ? "fwd" : "back");
    setStep(to);
  }

  function next() {
    if (!canNext) return;
    if (step === 1 && categories.length === 0) {
      // Pre-fill category suggestions from the role the first time we reach this step.
      const key = role.trim().toLowerCase();
      setCategories((CATEGORY_SUGGESTIONS[key] ?? CATEGORY_SUGGESTIONS.default).slice(0, 5));
    }
    if (step === 3) save.mutate();
    else go(step + 1);
  }

  const roleKey = role.trim().toLowerCase();
  const categorySuggestions = CATEGORY_SUGGESTIONS[roleKey] ?? CATEGORY_SUGGESTIONS.default;

  const heading = [
    { title: `Hi ${name}, what do you do?`, desc: "Your twin adapts its suggestions to your role." },
    { title: "What are you working towards?", desc: `Pick up to ${MAX_GOALS}. Your twin nudges you towards them.` },
    { title: "How do you spend your time?", desc: `These become the categories you log activities in. Up to ${MAX_CATEGORIES}.` },
    { title: "Five quick questions", desc: "A first sketch of your personality. Your real data replaces it after about two weeks." },
  ][step];

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-16 items-center justify-between border-b bg-card px-5 sm:px-8">
        <Wordmark />
        <span className="font-mono text-xs text-muted-foreground">
          Step {step + 1} of {STEPS.length}
        </span>
      </header>

      {/* Progress */}
      <div className="h-[3px] bg-secondary" aria-hidden>
        <div
          className="h-full bg-primary transition-[width] duration-500 ease-out"
          style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
        />
      </div>

      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-5 py-10 sm:px-8 sm:py-14">
        <ol className="mb-10 hidden gap-6 sm:flex" aria-label="Onboarding progress">
          {STEPS.map((s, i) => (
            <li
              key={s}
              aria-current={i === step ? "step" : undefined}
              className={cn(
                "flex items-center gap-2 text-sm transition-colors duration-300",
                i === step ? "font-semibold text-foreground" : "text-muted-foreground",
              )}
            >
              <span
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-md font-mono text-[11px] transition-colors duration-300",
                  i < step && "bg-primary text-primary-foreground",
                  i === step && "bg-foreground text-background",
                  i > step && "border text-muted-foreground",
                )}
              >
                {i < step ? (
                  <Check className="h-3.5 w-3.5 animate-pop" strokeWidth={3} aria-hidden />
                ) : (
                  String(i + 1).padStart(2, "0")
                )}
              </span>
              {s}
            </li>
          ))}
        </ol>

        <div
          key={step}
          className={cn(dir === "fwd" ? "animate-slide-in-right" : "animate-slide-in-left")}
        >
          <h1 className="text-[28px] font-semibold leading-tight sm:text-[34px]">{heading.title}</h1>
          <p className="mt-2 text-[15px] text-muted-foreground">{heading.desc}</p>

          <div className="mt-8">
            {step === 0 && (
              <div className="flex flex-col gap-6">
                <div className="flex flex-wrap gap-2">
                  {ROLES.map((r) => (
                    <Chip key={r} selected={role === r} onClick={() => setRole(r)}>
                      {r}
                    </Chip>
                  ))}
                </div>
                <div className="flex max-w-md flex-col gap-2">
                  <Label htmlFor="role">Or describe it yourself</Label>
                  <Input
                    id="role"
                    placeholder="e.g. Nurse on night shifts"
                    maxLength={120}
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && next()}
                  />
                </div>
              </div>
            )}

            {step === 1 && (
              <ListPicker
                values={goals}
                onChange={setGoals}
                suggestions={GOAL_SUGGESTIONS}
                max={MAX_GOALS}
                inputLabel="Add your own goal"
                placeholder="e.g. Read 20 pages a day"
              />
            )}

            {step === 2 && (
              <ListPicker
                values={categories}
                onChange={setCategories}
                suggestions={categorySuggestions}
                max={MAX_CATEGORIES}
                inputLabel="Add a category"
                placeholder="e.g. Gym"
              />
            )}

            {step === 3 && (
              <div className="flex flex-col divide-y rounded-lg border bg-card shadow-card">
                {QUIZ.map((q, i) => (
                  <fieldset
                    key={q.key}
                    className="flex animate-fade-up flex-col gap-3 p-5"
                    style={{ animationDelay: `${i * 50}ms` }}
                  >
                    <legend className="contents">
                      <span className="flex gap-3 text-[15px] font-semibold">
                        <span className="font-mono text-xs font-medium leading-6 text-primary">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        {q.text}
                      </span>
                    </legend>
                    <div className="flex flex-wrap gap-2 sm:pl-7">
                      {q.options.map((o) => (
                        <Chip
                          key={String(o.value)}
                          selected={quiz[q.key] === o.value}
                          onClick={() => setQuiz((prev) => ({ ...prev, [q.key]: o.value }))}
                        >
                          {o.label}
                        </Chip>
                      ))}
                    </div>
                  </fieldset>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="mt-auto pt-10">
          <FormError message={save.error?.message} className="mb-4" />
          <div className="flex items-center justify-between gap-3 border-t pt-6">
            <Button
              variant="ghost"
              onClick={() => go(step - 1)}
              disabled={step === 0 || save.isPending}
              className={cn(step === 0 && "invisible")}
            >
              <ArrowLeft /> Back
            </Button>
            <div className="flex items-center gap-4">
              {step === 3 && (
                <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
                  {answered}/{QUIZ.length} answered
                </span>
              )}
              <Button size="lg" onClick={next} disabled={!canNext || save.isPending} className="group">
                {save.isPending && <Spinner className="text-primary-foreground" />}
                {step === 3 ? "Create my twin" : "Next"}
                {!save.isPending && (
                  <ArrowRight className="transition-transform duration-200 group-hover:translate-x-0.5" />
                )}
              </Button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function ListPicker({
  values,
  onChange,
  suggestions,
  max,
  inputLabel,
  placeholder,
}: {
  values: string[];
  onChange: (v: string[]) => void;
  suggestions: string[];
  max: number;
  inputLabel: string;
  placeholder: string;
}) {
  const [draft, setDraft] = useState("");
  const has = (v: string) => values.some((x) => x.toLowerCase() === v.toLowerCase());
  const full = values.length >= max;

  function toggle(v: string) {
    if (has(v)) onChange(values.filter((x) => x.toLowerCase() !== v.toLowerCase()));
    else if (!full) onChange([...values, v]);
  }

  function addDraft() {
    const v = draft.trim().slice(0, 60);
    if (v && !has(v) && !full) onChange([...values, v]);
    setDraft("");
  }

  const custom = values.filter((v) => !suggestions.some((s) => s.toLowerCase() === v.toLowerCase()));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s) => (
          <Chip key={s} tick selected={has(s)} onClick={() => toggle(s)} disabled={!has(s) && full}>
            {s}
          </Chip>
        ))}
        {custom.map((v) => (
          <Chip
            key={v}
            selected
            onClick={() => toggle(v)}
            aria-label={`Remove ${v}`}
            className="animate-pop"
          >
            {v}
            <X className="h-3.5 w-3.5" aria-hidden />
          </Chip>
        ))}
      </div>
      <div className="flex max-w-md flex-col gap-2">
        <div className="flex items-baseline justify-between">
          <Label htmlFor="custom-item">{inputLabel}</Label>
          <span className="font-mono text-xs text-muted-foreground">
            {values.length}/{max} selected
          </span>
        </div>
        <div className="flex gap-2">
          <Input
            id="custom-item"
            placeholder={placeholder}
            value={draft}
            maxLength={60}
            disabled={full}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addDraft();
              }
            }}
          />
          <Button
            type="button"
            variant="outline"
            className="h-11 w-11 shrink-0 px-0"
            onClick={addDraft}
            disabled={!draft.trim() || full}
            aria-label="Add"
          >
            <Plus />
          </Button>
        </div>
      </div>
    </div>
  );
}
