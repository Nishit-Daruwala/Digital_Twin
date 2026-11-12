"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
    <Card>
      <CardHeader>
        <CardTitle>{isRegister ? "Create your twin" : "Welcome back"}</CardTitle>
        <CardDescription>
          {isRegister
            ? "Your twin learns from your days and helps you plan better ones."
            : "Log in to talk to your twin."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
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
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete={isRegister ? "new-password" : "current-password"}
              required
              minLength={isRegister ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {isRegister && <p className="text-xs text-muted-foreground">At least 8 characters.</p>}
          </div>
          <FormError message={error} />
          <Button type="submit" disabled={busy || !email || !password || (isRegister && !name)}>
            {busy && <Spinner className="text-primary-foreground" />}
            {isRegister ? "Create account" : "Log in"}
          </Button>
        </form>
        <p className="mt-5 text-center text-sm text-muted-foreground">
          {isRegister ? "Already have a twin? " : "New here? "}
          <Link
            href={isRegister ? "/login" : "/register"}
            className="font-medium text-primary hover:underline"
          >
            {isRegister ? "Log in" : "Create an account"}
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
