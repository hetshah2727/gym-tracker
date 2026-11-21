"use client";

import { Phone, X } from "lucide-react";
import { useEffect, useState } from "react";
import { SourceBadge, useAction } from "@/components/shared/growth";
import { Badge, Button, Field, Input, Loading, Select } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { usePlans } from "@/hooks/useLookups";
import { formatCurrency, formatDateTime, humanize } from "@/lib/utils";
import { post } from "@/services/api";

export const STAGES = ["new", "contacted", "interested", "trial_booked", "trial_attended", "negotiation", "converted", "lost"] as const;
export const stageLabel = (s: string) => (s === "converted" ? "Joined" : humanize(s));

export interface LeadRow {
  id: string; name: string; phone: string | null; email: string | null; source: string; status: string; priority: string;
  score: number; score_reasons: { points: number; reason: string }[]; attribution: Record<string, unknown>;
  fitness_interest: string | null; wants_trial: boolean; assigned_to_id: string | null; created_at: string;
  first_response_at: string | null; last_contacted_at: string | null; next_follow_up_at: string | null;
  lost_reason: string | null; existing_member_id: string | null; converted_member_id: string | null; message: string | null;
  whatsapp_opt_in: boolean; opted_out: boolean;
}
interface Detail {
  lead: LeadRow;
  interested_plan: { name: string; price: number } | null;
  campaign: { name: string } | null;
  interactions: { id: string; kind: string; direction: string | null; body: string | null; created_at: string; data: Record<string, unknown> }[];
  tasks: { id: string; title: string; status: string; due_at: string | null; draft_message: string | null }[];
  trials: { id: string; starts_at: string; status: string }[];
}

export function LeadDrawer({ leadId, onClose, onChanged }: { leadId: string | null; onClose: () => void; onChanged: () => void }) {
  const { data, loading, reload } = useApi<Detail>(leadId ? `/crm/leads/${leadId}` : null);
  const { plans } = usePlans();
  const slots = useApi<{ starts_at: string; remaining: number }[]>(leadId ? "/trials/slots" : null, { days: 7 });
  const { busy, run } = useAction();
  const [note, setNote] = useState({ kind: "call", body: "" });
  const [stage, setStage] = useState("");
  const [lost, setLost] = useState("");
  const [convert, setConvert] = useState({ plan_id: "", paid: true, payment_method: "upi" });
  const [slot, setSlot] = useState("");
  useEffect(() => { if (data) setStage(data.lead.status); }, [data]);
  if (!leadId) return null;
  const done = () => { reload(); onChanged(); };
  const l = data?.lead;
  const closed = l && ["converted", "lost"].includes(l.status);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
      <aside role="dialog" aria-label="Lead details" className="h-full w-full max-w-xl overflow-y-auto border-l border-border bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">{l?.name ?? "Lead"}</h2>
            {l && <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
              <Badge value={l.status === "converted" ? "converted" : l.status} />
              <span>{humanize(l.source)}</span>
              <span>· attribution: {String(l.attribution?.method ?? "unknown")}</span>
              {data?.campaign && <span>· {data.campaign.name}</span>}
              {l.existing_member_id && <Badge value="active" className="!bg-sky-500/15 !text-sky-400" />}
            </div>}
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-muted hover:bg-surface-2"><X className="h-4 w-4" /></button>
        </div>
        {loading || !l || !data ? <Loading /> : (
          <div className="space-y-5 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div><p className="label">Phone</p>{l.phone ? <a href={`tel:${l.phone}`} className="inline-flex items-center gap-1 text-brand"><Phone className="h-3.5 w-3.5" />{l.phone}</a> : "—"}</div>
              <div><p className="label">Email</p>{l.email ?? "—"}</div>
              <div><p className="label">Interest</p>{l.fitness_interest ?? "—"}{l.wants_trial && " · wants trial"}</div>
              <div><p className="label">Preferred plan</p>{data.interested_plan ? `${data.interested_plan.name} (${formatCurrency(data.interested_plan.price)})` : "—"}</div>
              <div><p className="label">First response</p>{l.first_response_at ? formatDateTime(l.first_response_at) : <span className="text-warning">Not yet</span>}</div>
              <div><p className="label">WhatsApp</p>{l.opted_out ? "Opted out" : l.whatsapp_opt_in ? "Opted in" : "No opt-in"}</div>
            </div>
            {l.existing_member_id && <p className="rounded-lg bg-sky-500/10 px-3 py-2 text-xs text-sky-400">This phone/email belongs to an existing member.</p>}

            <section>
              <p className="label">Lead score: <span className="text-fg">{l.score}</span> ({humanize(l.priority)} priority)</p>
              <ul className="mt-1 space-y-0.5 text-xs text-muted">
                {l.score_reasons.map((r, i) => <li key={i}><span className={r.points > 0 ? "text-brand" : "text-danger"}>{r.points > 0 ? "+" : ""}{r.points}</span> {r.reason}</li>)}
              </ul>
            </section>

            {!closed && <section className="card space-y-3 p-3">
              <p className="font-medium">Log contact</p>
              <div className="flex gap-2">
                <Select className="w-32" value={note.kind} onChange={(e) => setNote({ ...note, kind: e.target.value })} options={["call", "whatsapp", "email", "visit", "note"]} />
                <Input value={note.body} onChange={(e) => setNote({ ...note, body: e.target.value })} placeholder="What happened?" />
                <Button loading={busy === "note"} onClick={() => run("note", () => post(`/crm/leads/${l.id}/interactions`, { kind: note.kind, body: note.body || undefined }), "Logged").then((r) => { if (r) { setNote({ kind: "call", body: "" }); done(); } })}>Save</Button>
              </div>
            </section>}

            {!closed && <section className="card space-y-3 p-3">
              <p className="font-medium">Move stage</p>
              <div className="flex flex-wrap gap-2">
                <Select className="w-44" value={stage} onChange={(e) => setStage(e.target.value)} options={STAGES.filter((s) => s !== "converted").map((s) => ({ value: s, label: stageLabel(s) }))} />
                {stage === "lost" && <Input className="flex-1" value={lost} onChange={(e) => setLost(e.target.value)} placeholder="Lost reason (required)" />}
                <Button variant="secondary" disabled={stage === l.status || (stage === "lost" && !lost)} loading={busy === "stage"}
                  onClick={() => run("stage", () => post(`/crm/leads/${l.id}/status`, { status: stage, lost_reason: lost || undefined }), "Stage updated").then((r) => r && done())}>Update</Button>
              </div>
            </section>}

            {!closed && <section className="card space-y-3 p-3">
              <p className="font-medium">Book a trial</p>
              <div className="flex gap-2">
                <Select value={slot} onChange={(e) => setSlot(e.target.value)} placeholder="Choose a slot"
                  options={(slots.data ?? []).map((s) => ({ value: s.starts_at, label: `${formatDateTime(s.starts_at)} · ${s.remaining} left` }))} />
                <Button disabled={!slot} loading={busy === "trial"} onClick={() => run("trial", () => post(`/trials`, { lead_id: l.id, starts_at: slot, source: "crm" }), "Trial booked").then((r) => r && done())}>Book</Button>
              </div>
            </section>}

            {!closed && <section className="card space-y-3 p-3">
              <p className="font-medium">Convert to member</p>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Plan"><Select value={convert.plan_id} onChange={(e) => setConvert({ ...convert, plan_id: e.target.value })} placeholder="Select plan" options={plans.map((p) => ({ value: p.id, label: `${p.name} · ${formatCurrency(p.price)}` }))} /></Field>
                <Field label="Payment"><Select value={convert.paid ? convert.payment_method : "unpaid"} onChange={(e) => setConvert({ ...convert, paid: e.target.value !== "unpaid", payment_method: e.target.value === "unpaid" ? "upi" : e.target.value })}
                  options={[{ value: "upi", label: "Paid - UPI" }, { value: "cash", label: "Paid - cash" }, { value: "card", label: "Paid - card" }, { value: "unpaid", label: "Not paid yet" }]} /></Field>
              </div>
              <p className="text-xs text-muted">Creates the member, membership and a payment record. Revenue counts only once the payment is paid.</p>
              <Button disabled={!convert.plan_id} loading={busy === "convert"} onClick={() => run("convert", () => post(`/crm/leads/${l.id}/convert`, convert), "Converted - welcome aboard!").then((r) => r && done())}>Convert</Button>
            </section>}
            {l.lost_reason && <p className="text-xs text-muted">Lost reason: {l.lost_reason}</p>}

            {data.tasks.length > 0 && <section>
              <p className="label">Tasks</p>
              <ul className="space-y-1">{data.tasks.map((t) => <li key={t.id} className="flex items-center justify-between rounded-lg bg-surface-2 px-3 py-2 text-xs"><span>{t.title}{t.draft_message && <span className="block text-muted">Draft: {t.draft_message}</span>}</span><Badge value={t.status === "done" ? "paid" : t.status === "open" ? "pending" : "cancelled"} /></li>)}</ul>
            </section>}
            {data.trials.length > 0 && <section>
              <p className="label">Trials</p>
              <ul className="space-y-1 text-xs">{data.trials.map((t) => <li key={t.id} className="flex justify-between rounded-lg bg-surface-2 px-3 py-2"><span>{formatDateTime(t.starts_at)}</span><span>{humanize(t.status)}</span></li>)}</ul>
            </section>}
            <section>
              <p className="label">Timeline</p>
              <ol className="space-y-2 border-l border-border pl-4">
                {data.interactions.map((i) => (
                  <li key={i.id} className="text-xs">
                    <p className="text-muted">{formatDateTime(i.created_at)} · {humanize(i.kind)}{i.direction ? ` (${i.direction === "in" ? "from lead" : "to lead"})` : ""}{i.data?.by === "ai_agent" && <SourceBadge source="claude" className="ml-1" />}</p>
                    {i.body && <p className="mt-0.5 whitespace-pre-line">{i.body}</p>}
                  </li>
                ))}
              </ol>
            </section>
          </div>
        )}
      </aside>
    </div>
  );
}
