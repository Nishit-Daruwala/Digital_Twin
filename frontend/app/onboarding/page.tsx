"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { api } from "@/lib/api";
import { qk } from "@/lib/hooks";
import type { QuizAnswers } from "@/lib/types";
import { AuthGuard } from "@/components/auth-guard";
import { Logo } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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

  const canNext = [
    role.trim().length > 0,
    goals.length > 0,
    categories.length > 0,
    QUIZ.every((q) => quiz[q.key] !== undefined),
  ][step];

  function goToCategories() {
    // Pre-fill category suggestions from the role the first time we reach this step.
    if (categories.length === 0) {
      const key = role.trim().toLowerCase();
      setCategories((CATEGORY_SUGGESTIONS[key] ?? CATEGORY_SUGGESTIONS.default).slice(0, 5));
    }
    setStep(2);
  }

  function next() {
    if (!canNext) return;
    if (step === 1) goToCategories();
    else if (step === 3) save.mutate();
    else setStep(step + 1);
  }

  const roleKey = role.trim().toLowerCase();
  const categorySuggestions = CATEGORY_SUGGESTIONS[roleKey] ?? CATEGORY_SUGGESTIONS.default;

  return (
    <div className="flex min-h-dvh flex-col items-center bg-secondary/40 px-4 py-8">
      <div className="mb-6 flex items-center gap-2">
        <Logo />
        <span className="text-xl font-semibold">Twin</span>
      </div>

      <div className="w-full max-w-lg">
        <ol className="mb-4 flex gap-2" aria-label="Onboarding progress">
          {STEPS.map((s, i) => (
            <li key={s} className="flex-1">
              <div
                className={cn("h-1.5 rounded-full", i <= step ? "bg-primary" : "bg-border")}
                aria-hidden
              />
              <span
                className={cn(
                  "mt-1 block text-xs",
                  i === step ? "font-medium text-foreground" : "text-muted-foreground",
                )}
                aria-current={i === step ? "step" : undefined}
              >
                {s}
              </span>
            </li>
          ))}
        </ol>

        <Card>
          {step === 0 && (
            <>
              <CardHeader>
                <CardTitle>Hi {name}, what do you do?</CardTitle>
                <CardDescription>Your twin adapts its suggestions to your role.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="flex flex-wrap gap-2">
                  {ROLES.map((r) => (
                    <Chip key={r} selected={role === r} onClick={() => setRole(r)}>
                      {r}
                    </Chip>
                  ))}
                </div>
                <div className="flex flex-col gap-2">
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
              </CardContent>
            </>
          )}

          {step === 1 && (
            <>
              <CardHeader>
                <CardTitle>What are your goals?</CardTitle>
                <CardDescription>Pick up to {MAX_GOALS}. Your twin nudges you towards them.</CardDescription>
              </CardHeader>
              <CardContent>
                <ListPicker
                  values={goals}
                  onChange={setGoals}
                  suggestions={GOAL_SUGGESTIONS}
                  max={MAX_GOALS}
                  inputLabel="Add your own goal"
                  placeholder="e.g. Read 20 pages a day"
                />
              </CardContent>
            </>
          )}

          {step === 2 && (
            <>
              <CardHeader>
                <CardTitle>How do you spend your time?</CardTitle>
                <CardDescription>
                  These categories are used to log activities. Up to {MAX_CATEGORIES}.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ListPicker
                  values={categories}
                  onChange={setCategories}
                  suggestions={categorySuggestions}
                  max={MAX_CATEGORIES}
                  inputLabel="Add a category"
                  placeholder="e.g. Gym"
                />
              </CardContent>
            </>
          )}

          {step === 3 && (
            <>
              <CardHeader>
                <CardTitle>Five quick questions</CardTitle>
                <CardDescription>
                  A first guess at your personality. Your real data replaces it after ~2 weeks.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-5">
                {QUIZ.map((q) => (
                  <fieldset key={q.key} className="flex flex-col gap-2">
                    <legend className="mb-2 text-sm font-medium">{q.text}</legend>
                    <div className="flex flex-wrap gap-2">
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
              </CardContent>
            </>
          )}

          <div className="flex flex-col gap-3 p-5 pt-0">
            <FormError message={save.error?.message} />
            <div className="flex justify-between gap-3">
              <Button
                variant="ghost"
                onClick={() => setStep(step - 1)}
                disabled={step === 0 || save.isPending}
              >
                Back
              </Button>
              <Button onClick={next} disabled={!canNext || save.isPending}>
                {save.isPending && <Spinner className="text-primary-foreground" />}
                {step === 3 ? "Create my twin" : "Next"}
              </Button>
            </div>
          </div>
        </Card>
      </div>
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
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s) => (
          <Chip key={s} selected={has(s)} onClick={() => toggle(s)} disabled={!has(s) && full}>
            {s}
          </Chip>
        ))}
        {custom.map((v) => (
          <Chip key={v} selected onClick={() => toggle(v)} aria-label={`Remove ${v}`}>
            {v}
            <X className="h-3.5 w-3.5" aria-hidden />
          </Chip>
        ))}
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="custom-item">{inputLabel}</Label>
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
            size="icon"
            onClick={addDraft}
            disabled={!draft.trim() || full}
            aria-label="Add"
          >
            <Plus />
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          {values.length}/{max} selected
        </p>
      </div>
    </div>
  );
}
