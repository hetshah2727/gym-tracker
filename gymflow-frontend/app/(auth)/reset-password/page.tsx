"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { Button, ErrorNote, Field, Input } from "@/components/shared/ui";
import { homeFor, resetPassword } from "@/services/auth";

function ResetForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (password !== confirm) return setError("The two passwords don't match");
    setLoading(true);
    setError(null);
    try {
      const user = await resetPassword(token, password);
      router.replace(homeFor(user.role));
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset the password");
      setLoading(false);
    }
  }

  if (!token) {
    return <p className="text-sm text-muted">This link is incomplete. <Link href="/forgot-password" className="text-brand">Ask for a new one</Link>.</p>;
  }
  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <h1 className="font-display text-2xl font-bold">Choose a new password</h1>
        <p className="text-sm text-muted">At least 8 characters.</p>
      </div>
      <ErrorNote message={error} />
      <Field label="New password"><Input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
      <Field label="Type it again"><Input type="password" required minLength={8} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>
      <Button type="submit" loading={loading} className="w-full">Save and log in</Button>
      <p className="text-center text-sm text-muted">Link expired? <Link href="/forgot-password" className="text-brand">Send a new one</Link></p>
    </form>
  );
}

export default function ResetPasswordPage() {
  return <Suspense><ResetForm /></Suspense>;
}
