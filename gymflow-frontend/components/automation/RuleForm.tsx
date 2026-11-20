"use client";

import { useState, type FormEvent } from "react";
import { Button, ErrorNote, Field, Input, Select, Textarea } from "@/components/shared/ui";
import { patch, post } from "@/services/api";
import type { AutomationRule, AutomationTrigger } from "@/types";

export const TRIGGERS: { value: AutomationTrigger; label: string; offsetLabel: string; placeholders: string }[] = [
  { value: "membership_expiring", label: "Membership expiring", offsetLabel: "Days before expiry", placeholders: "{name} {gym} {end_date} {days_left}" },
  { value: "membership_expired", label: "Membership expired", offsetLabel: "Days after expiry", placeholders: "{name} {gym} {end_date}" },
  { value: "payment_due", label: "Payment due", offsetLabel: "Days before due date", placeholders: "{name} {gym} {amount} {currency} {due_date}" },
  { value: "birthday", label: "Member birthday", offsetLabel: "(not used)", placeholders: "{name} {gym}" },
  { value: "inactive_member", label: "Member inactive", offsetLabel: "Days without a check-in", placeholders: "{name} {gym} {days}" },
];

export function RuleForm({ rule, onSaved }: { rule?: AutomationRule; onSaved: () => void }) {
  const [form, setForm] = useState({
    name: rule?.name ?? "",
    trigger: rule?.trigger ?? "membership_expiring",
    offset_days: String(rule?.offset_days ?? 3),
    channel: rule?.channel ?? "whatsapp",
    template: rule?.template ?? "Hi {name}, your {gym} membership expires on {end_date}. Renew to keep going!",
    n8n_workflow: rule?.n8n_workflow ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const meta = TRIGGERS.find((t) => t.value === form.trigger)!;
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const body = { ...form, offset_days: Number(form.offset_days), n8n_workflow: form.n8n_workflow || null };
    try {
      if (rule) {
        const { trigger: _t, ...update } = body; // trigger is fixed once created
        void _t;
        await patch(`/automation/rules/${rule.id}`, update);
      } else {
        await post("/automation/rules", body);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save rule");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <ErrorNote message={error} />
      <Field label="Rule name"><Input required value={form.name} onChange={set("name")} placeholder="3-day expiry reminder" /></Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="When">
          <Select value={form.trigger} onChange={set("trigger")} disabled={!!rule} options={TRIGGERS.map((t) => ({ value: t.value, label: t.label }))} />
        </Field>
        <Field label={meta.offsetLabel}><Input type="number" min={0} value={form.offset_days} onChange={set("offset_days")} /></Field>
        <Field label="Channel"><Select value={form.channel} onChange={set("channel")} options={[{ value: "whatsapp", label: "WhatsApp" }, { value: "voice", label: "AI voice call" }, { value: "sms", label: "SMS" }, { value: "email", label: "Email" }]} /></Field>
      </div>
      <Field label="Message" hint={`Placeholders: ${meta.placeholders}`}>
        <Textarea rows={4} required value={form.template} onChange={set("template")} />
      </Field>
      <Field label="n8n workflow (optional)" hint="Webhook path to also notify an n8n workflow when this rule fires">
        <Input value={form.n8n_workflow} onChange={set("n8n_workflow")} placeholder="renewal-followup" />
      </Field>
      <div className="flex justify-end"><Button type="submit" loading={saving}>{rule ? "Save rule" : "Create rule"}</Button></div>
    </form>
  );
}
