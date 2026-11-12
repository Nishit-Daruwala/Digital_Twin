"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormError } from "@/components/ui/alert";
import { Spinner } from "@/components/spinner";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isRegister = mode === "register";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (isRegister && password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      if (isRegister) await api.register(email, password, name);
      else await api.login(email, password);
      qc.clear(); // drop any cached data from a previous user
      router.replace(isRegister ? "/onboarding" : "/chat");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="eyebrow mb-3 text-primary">{isRegister ? "Get started" : "Welcome back"}</p>
      <h2 className="text-[28px] font-semibold leading-tight">
        {isRegister ? "Create your twin" : "Log in to Twin"}
      </h2>
      <p className="mt-2 text-[15px] text-muted-foreground">
        {isRegister
          ? "It learns from your days and helps you plan better ones."
          : "Pick up where your twin left off."}
      </p>

      <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-5" noValidate>
        {isRegister && (
          <div className="flex flex-col gap-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              autoComplete="name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
        )}
        <div className="flex flex-col gap-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPw ? "text" : "password"}
              autoComplete={isRegister ? "new-password" : "current-password"}
              required
              minLength={isRegister ? 8 : undefined}
              className="pr-11"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button
              type="button"
              onClick={() => setShowPw((s) => !s)}
              aria-label={showPw ? "Hide password" : "Show password"}
              className="absolute right-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {isRegister && <p className="text-xs text-muted-foreground">At least 8 characters.</p>}
        </div>

        <FormError message={error} />

        <Button
          type="submit"
          size="lg"
          className="group mt-1"
          disabled={busy || !email || !password || (isRegister && !name)}
        >
          {busy && <Spinner className="text-primary-foreground" />}
          {isRegister ? "Create account" : "Log in"}
          {!busy && (
            <ArrowRight
              className="transition-transform duration-200 group-hover:translate-x-0.5"
              aria-hidden
            />
          )}
        </Button>
      </form>

      <p className="mt-8 border-t pt-6 text-sm text-muted-foreground">
        {isRegister ? "Already have a twin? " : "New to Twin? "}
        <Link
          href={isRegister ? "/login" : "/register"}
          className="font-semibold text-primary underline-offset-4 hover:underline"
        >
          {isRegister ? "Log in" : "Create an account"}
        </Link>
      </p>
    </div>
  );
}
