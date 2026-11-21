"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { DEMO_ENABLED, DemoButton } from "@/components/marketing/DemoButton";
import { Button, ErrorNote, Field, Input } from "@/components/shared/ui";
import { homeFor, login } from "@/services/auth";

function LoginForm() {
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const user = await login(email, password);
      router.replace(next && next.startsWith("/") ? next : homeFor(user.role));
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <h1 className="font-display text-2xl font-bold">Welcome back</h1>
        <p className="text-sm text-muted">Gym owners, staff and members all log in here.</p>
      </div>
      <ErrorNote message={error} />
      <Field label="Email">
        <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Password">
        <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <div className="flex justify-end">
        <Link href="/forgot-password" className="text-xs text-muted hover:text-fg">Forgot password?</Link>
      </div>
      <Button type="submit" loading={loading} className="w-full">Log in</Button>
      {DEMO_ENABLED && <>
        <div className="flex items-center gap-3 text-xs text-muted"><span className="h-px flex-1 bg-border" />or<span className="h-px flex-1 bg-border" /></div>
        <DemoButton className="w-full" label="Look around a sample gym first" />
      </>}
      <p className="text-center text-sm text-muted">
        New gym? <Link href="/register" className="font-semibold text-brand">Start a free trial</Link>
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
