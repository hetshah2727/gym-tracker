"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Button, ErrorNote, Field, Input } from "@/components/shared/ui";
import { requestPasswordReset } from "@/services/auth";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setSent((await requestPasswordReset(email)).detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <h1 className="font-display text-2xl font-bold">Reset your password</h1>
        <p className="text-sm text-muted">We&apos;ll email you a link to choose a new one. It works for 30 minutes.</p>
      </div>
      <ErrorNote message={error} />
      {sent ? (
        <p className="rounded-xl border border-money/40 bg-money/10 px-3 py-2 text-sm text-money">{sent} Check your inbox (and spam folder).</p>
      ) : (
        <>
          <Field label="Email">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Button type="submit" loading={loading} className="w-full">Send reset link</Button>
        </>
      )}
      <p className="text-center text-sm text-muted">
        <Link href="/login" className="text-brand">Back to log in</Link>
      </p>
    </form>
  );
}
