"use client";

import { CheckCircle2, Send, Sparkles, Trash2, Utensils } from "lucide-react";
import { useState, type FormEvent } from "react";
import { DietPlanView } from "@/components/diet/DietPlanView";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, Loading, Modal, PageHeader, Select, Textarea } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { useMemberNames } from "@/hooks/useLookups";
import { formatDate } from "@/lib/utils";
import { del, patch, post } from "@/services/api";
import type { DietPlan, Member } from "@/types";

export default function DietPlansPage() {
  const { data, loading, error, reload } = useApi<DietPlan[]>("/diet-plans");
  const { members, names } = useMemberNames();
  const [generating, setGenerating] = useState(false);
  const [open, setOpen] = useState<DietPlan | null>(null);

  return (
    <>
      <PageHeader
        title="AI diet plans"
        description="Generate a plan from a member's profile, review it, then assign it to them."
        actions={<Button onClick={() => setGenerating(true)}><Sparkles className="h-4 w-4" /> Generate plan</Button>}
      />
      <Card>
        {error && <div className="p-4"><ErrorNote message={error} /></div>}
        {loading && !data ? (
          <Loading />
        ) : !data?.length ? (
          <EmptyState icon={<Utensils className="h-8 w-8" />} title="No diet plans yet" description="Generate one for a member — it starts as a draft for you to review." />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead><tr><th>Member</th><th>Plan</th><th>Calories</th><th>Status</th><th>Updated</th></tr></thead>
              <tbody>
                {data.map((p) => (
                  <tr key={p.id} className="cursor-pointer hover:bg-surface-2/50" onClick={() => setOpen(p)}>
                    <td className="font-medium">{names[p.member_id] ?? "—"}</td>
                    <td className="text-muted">{p.title}</td>
                    <td className="tabular-nums">{p.daily_calories} kcal</td>
                    <td><Badge value={p.status} /></td>
                    <td className="text-muted">{formatDate(p.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={generating} onClose={() => setGenerating(false)} title="Generate diet plan">
        {generating && <GenerateForm members={members} onDone={(plan) => { setGenerating(false); reload(); setOpen(plan); }} />}
      </Modal>
      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? `${open.title}` : ""} wide>
        {open && <PlanReview plan={open} memberName={names[open.member_id]} onChange={(p) => { setOpen(p); reload(); }} onDeleted={() => { setOpen(null); reload(); }} />}
      </Modal>
    </>
  );
}

function GenerateForm({ members, onDone }: { members: Member[]; onDone: (p: DietPlan) => void }) {
  const [memberId, setMemberId] = useState("");
  const [cuisine, setCuisine] = useState("Indian");
  const [meals, setMeals] = useState("5");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const member = members.find((m) => m.id === memberId);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(await post<DietPlan>("/diet-plans/generate", { member_id: memberId, cuisine, meals_per_day: Number(meals), trainer_notes: notes || undefined }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <ErrorNote message={error} />
      <Field label="Member">
        <Select required value={memberId} onChange={(e) => setMemberId(e.target.value)} placeholder="Select member" options={members.map((m) => ({ value: m.id, label: m.full_name }))} />
      </Field>
      {member && (
        <p className="rounded-lg bg-surface-2 px-3 py-2 text-xs text-muted">
          {member.height_cm ?? "?"} cm · {member.weight_kg ?? "?"} kg · {member.fitness_goal?.replace("_", " ") ?? "no goal"} · {member.diet_preference?.replace("_", "-") ?? "no diet preference"}
          {member.dietary_restrictions && ` · avoid: ${member.dietary_restrictions}`}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Cuisine"><Input value={cuisine} onChange={(e) => setCuisine(e.target.value)} /></Field>
        <Field label="Meals per day"><Select value={meals} onChange={(e) => setMeals(e.target.value)} options={["3", "4", "5", "6"].map((v) => ({ value: v, label: v }))} /></Field>
      </div>
      <Field label="Notes for the AI (optional)"><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Trains at 6 pm, budget-friendly, prefers home-cooked food" /></Field>
      <div className="flex items-center justify-end gap-3">
        {busy && <span className="text-xs text-muted">This can take up to a minute…</span>}
        <Button type="submit" loading={busy} disabled={!memberId}><Sparkles className="h-4 w-4" /> Generate</Button>
      </div>
    </form>
  );
}

function PlanReview({ plan, memberName, onChange, onDeleted }: { plan: DietPlan; memberName?: string; onChange: (p: DietPlan) => void; onDeleted: () => void }) {
  const [notes, setNotes] = useState(plan.notes ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(key: string, fn: () => Promise<DietPlan | void>) {
    setBusy(key);
    setError(null);
    try {
      const result = await fn();
      if (result) onChange(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted">For {memberName ?? "member"}</p>
      <ErrorNote message={error} />
      <DietPlanView plan={plan} />
      <Field label="Trainer notes (visible to the member)">
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
      <div className="flex flex-wrap justify-between gap-2">
        <Button variant="ghost" onClick={() => confirm("Delete this plan?") && run("delete", async () => { await del(`/diet-plans/${plan.id}`); onDeleted(); })}>
          <Trash2 className="h-4 w-4" /> Delete
        </Button>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" loading={busy === "save"} disabled={notes === (plan.notes ?? "")} onClick={() => run("save", () => patch<DietPlan>(`/diet-plans/${plan.id}`, { notes }))}>
            Save notes
          </Button>
          {plan.status === "draft" && (
            <Button variant="secondary" loading={busy === "approve"} onClick={() => run("approve", () => post<DietPlan>(`/diet-plans/${plan.id}/approve`))}>
              <CheckCircle2 className="h-4 w-4" /> Approve
            </Button>
          )}
          {plan.status !== "assigned" && (
            <Button loading={busy === "assign"} onClick={() => run("assign", () => post<DietPlan>(`/diet-plans/${plan.id}/assign`))}>
              <Send className="h-4 w-4" /> Assign &amp; notify member
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
