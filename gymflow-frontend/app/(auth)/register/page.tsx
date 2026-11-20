"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button, ErrorNote, Field, Input } from "@/components/shared/ui";
import { homeFor, register, type RegisterInput } from "@/services/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState<RegisterInput>({ gym_name: "", owner_name: "", email: "", password: "", phone: "", city: "" });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const set = (k: keyof RegisterInput) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const user = await register(form);
      router.replace(homeFor(user.role));
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-up failed");
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Create your gym workspace</h1>
        <p className="text-sm text-muted">14-day free trial. We set up default plans and reminders for you.</p>
      </div>
      <ErrorNote message={error} />
      <Field label="Gym name">
        <Input required value={form.gym_name} onChange={set("gym_name")} placeholder="Iron Temple Fitness" />
      </Field>
      <Field label="Your name">
        <Input required value={form.owner_name} onChange={set("owner_name")} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Phone (WhatsApp)">
          <Input value={form.phone} onChange={set("phone")} inputMode="tel" />
        </Field>
        <Field label="City">
          <Input value={form.city} onChange={set("city")} />
        </Field>
      </div>
      <Field label="Email">
        <Input type="email" required autoComplete="email" value={form.email} onChange={set("email")} />
      </Field>
      <Field label="Password" hint="At least 8 characters">
        <Input type="password" required minLength={8} autoComplete="new-password" value={form.password} onChange={set("password")} />
      </Field>
      <Button type="submit" loading={loading} className="w-full">Create gym</Button>
      <p className="text-center text-sm text-muted">
        Already registered? <Link href="/login" className="text-brand">Log in</Link>
      </p>
    </form>
  );
}
