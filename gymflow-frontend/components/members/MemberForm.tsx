"use client";

import { useState, type FormEvent } from "react";
import { Button, ErrorNote, Field, Input, Select, Textarea } from "@/components/shared/ui";
import { patch, post } from "@/services/api";
import type { Member, Trainer } from "@/types";

type FormState = Record<string, string>;

const FIELDS = [
  "full_name", "phone", "email", "gender", "date_of_birth", "height_cm", "weight_kg",
  "fitness_goal", "diet_preference", "dietary_restrictions", "trainer_id", "notes",
] as const;

function toForm(m?: Member): FormState {
  return Object.fromEntries(FIELDS.map((f) => [f, m?.[f] != null ? String(m[f]) : ""]));
}

export function MemberForm({ member, trainers, onSaved }: { member?: Member; trainers: Trainer[]; onSaved: (m: Member) => void }) {
  const [form, setForm] = useState<FormState>(toForm(member));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const body: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(form)) {
      if (v === "") body[k] = member ? null : undefined;
      else body[k] = k === "height_cm" || k === "weight_kg" ? Number(v) : v;
    }
    body.full_name = form.full_name;
    body.phone = form.phone;
    try {
      onSaved(member ? await patch<Member>(`/members/${member.id}`, body) : await post<Member>("/members", body));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <ErrorNote message={error} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Full name"><Input required value={form.full_name} onChange={set("full_name")} /></Field>
        <Field label="Phone (WhatsApp)"><Input required value={form.phone} onChange={set("phone")} inputMode="tel" /></Field>
        <Field label="Email"><Input type="email" value={form.email} onChange={set("email")} /></Field>
        <Field label="Date of birth"><Input type="date" value={form.date_of_birth} onChange={set("date_of_birth")} /></Field>
        <Field label="Gender"><Select value={form.gender} onChange={set("gender")} placeholder="—" options={["male", "female", "other"]} /></Field>
        <Field label="Trainer">
          <Select value={form.trainer_id} onChange={set("trainer_id")} placeholder="Unassigned"
            options={trainers.map((t) => ({ value: t.id, label: t.full_name }))} />
        </Field>
      </div>
      <p className="pt-1 text-xs font-medium uppercase tracking-wider text-muted">Fitness profile (used for AI diet plans)</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Height (cm)"><Input type="number" step="0.1" value={form.height_cm} onChange={set("height_cm")} /></Field>
        <Field label="Weight (kg)"><Input type="number" step="0.1" value={form.weight_kg} onChange={set("weight_kg")} /></Field>
        <Field label="Goal"><Select value={form.fitness_goal} onChange={set("fitness_goal")} placeholder="—" options={["weight_loss", "weight_gain", "maintenance"]} /></Field>
        <Field label="Diet preference">
          <Select value={form.diet_preference} onChange={set("diet_preference")} placeholder="—"
            options={[{ value: "veg", label: "Vegetarian" }, { value: "non_veg", label: "Non-vegetarian" }, { value: "eggetarian", label: "Eggetarian" }, { value: "vegan", label: "Vegan" }]} />
        </Field>
      </div>
      <Field label="Dietary restrictions / allergies"><Input value={form.dietary_restrictions} onChange={set("dietary_restrictions")} placeholder="e.g. lactose intolerant, no peanuts" /></Field>
      <Field label="Notes"><Textarea value={form.notes} onChange={set("notes")} /></Field>
      <div className="flex justify-end">
        <Button type="submit" loading={saving}>{member ? "Save changes" : "Add member"}</Button>
      </div>
    </form>
  );
}
