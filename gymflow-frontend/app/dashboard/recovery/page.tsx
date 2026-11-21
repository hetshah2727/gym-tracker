"use client";

import { Copy, Link2, RefreshCcw } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { FeatureGate, Kpi, Note, Pager, useAction, useQueryTab, useToast } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, InfoTip, Input, Loading, Modal, PageHeader, Select, Tabs } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, formatDate, formatDateTime, humanize } from "@/lib/utils";
import { post } from "@/services/api";
import type { Page } from "@/types";

type Tab = "renewals" | "expired" | "outstanding" | "failed" | "opportunities" | "history";
interface Opp { id: string; type: string; status: string; priority: string; title: string; reason: string; potential_revenue: number; recovered_revenue: number; next_action: string | null; due_date: string | null; milestones: string[]; contact_count: number; last_contacted_at: string | null; outcome: string | null; closed_at: string | null; recovered_payment_id: string | null }
interface Detail {
  opportunity: Opp; member: { name: string; phone: string } | null; lead: { name: string; phone: string | null } | null;
  membership: { plan: string | null; end_date: string; amount: number; status: string } | null;
  payment: { id: string; amount: number; status: string; due_date: string | null; failure_reason: string | null } | null;
  draft_message: string | null; tasks: { id: string; title: string; status: string; draft_message: string | null }[];
  creditable_payments: { id: string; amount: number; paid_at: string | null }[];
}
interface Summary { open_opportunities: number; expiring_7d: number; pending_payments: number; failed_payments: number; potential_value: number; revenue: { collected: number; recovered: number; outstanding: number; overdue: number; potential: number; forecast_next_30_days: number; definitions: Record<string, string> } }

const TAB_API: Record<Tab, string> = { renewals: "renewals", expired: "expired", outstanding: "outstanding", failed: "failed", opportunities: "", history: "history" };

export default function RecoveryPage() {
  const params = useSearchParams();
  const [tab, setTab] = useQueryTab<Tab>("renewals");
  const [type, setType] = useState(params.get("type") ?? "");
  const [offset, setOffset] = useState(0);
  const summary = useApi<Summary>("/recovery/summary");
  const list = useApi<Page<Opp>>("/recovery/opportunities", { tab: TAB_API[tab] || undefined, type: tab === "opportunities" ? type : undefined, offset, limit: 50 });
  const [open, setOpen] = useState<string | null>(null);
  const detail = useApi<Detail>(open ? `/recovery/opportunities/${open}` : null);
  const [note, setNote] = useState("");
  const [closeForm, setCloseForm] = useState({ status: "lost", outcome: "" });
  const [payId, setPayId] = useState("");
  const { busy, run } = useAction();
  const toast = useToast();
  const refresh = () => { list.reload(); summary.reload(); detail.reload(); };
  const s = summary.data;

  return (
    <FeatureGate feature="recovery_center">
      <PageHeader title="Renewals & late fees" description="Every renewal, late fee and missed trial GymFlow is following up – and the money it brought back."
        actions={<Button variant="secondary" loading={busy === "sync"} onClick={() => run("sync", () => post("/recovery/sync"), "Up to date").then(refresh)}><RefreshCcw className="h-4 w-4" /> Check again</Button>} />
      {s && <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label="Brought back this month" value={formatCurrency(s.revenue.recovered)} hint="Paid after a reminder" tone="brand" />
        <Kpi label="Unpaid fees" value={formatCurrency(s.revenue.outstanding)} hint={`${formatCurrency(s.revenue.overdue)} late`} tone={s.revenue.outstanding ? "danger" : undefined} />
        <Kpi label="Could still collect" value={formatCurrency(s.revenue.potential)} hint="If everyone renews and pays" />
        <Kpi label="Likely next 30 days" value={formatCurrency(s.revenue.forecast_next_30_days)} hint="Based on your past renewals" />
        <Kpi label="Expiring in 7 days" value={s.expiring_7d} hint={`${s.open_opportunities} people to follow up`} />
      </div>}
      <div className="mt-6"><Tabs<Tab> value={tab} onChange={(v) => { setTab(v); setOffset(0); }} tabs={[
        { value: "renewals", label: "Renewing soon" }, { value: "expired", label: "Ended" }, { value: "outstanding", label: "Unpaid fees" },
        { value: "failed", label: "Failed online payments" }, { value: "opportunities", label: "Everything" }, { value: "history", label: "Done" }]} /></div>
      {tab === "opportunities" && <Select className="mb-3 w-56" value={type} onChange={(e) => setType(e.target.value)} placeholder="All types" options={["upcoming_renewal", "expired_membership", "outstanding_payment", "failed_payment", "trial_no_show", "uncontacted_lead", "overdue_follow_up"]} />}
      <Card>
        {list.error && <div className="p-4"><ErrorNote message={list.error} /></div>}
        {list.loading ? <Loading /> : !list.data?.items.length ? <EmptyState title="Nothing here" description="GymFlow checks memberships, fees, trials and enquiries every day." /> : (
          <div className="overflow-x-auto"><table className="table-base">
            <thead><tr><th>Who</th><th>What</th><th>{tab === "history" ? "Brought back" : "Amount"}</th><th>{tab === "history" ? "Closed" : "Due"}</th><th>Status</th></tr></thead>
            <tbody>{list.data.items.map((o) => (
              <tr key={o.id} className="cursor-pointer hover:bg-surface-2" onClick={() => setOpen(o.id)}>
                <td><p className="font-medium">{o.title}</p><p className="text-xs text-muted">{o.reason}</p></td>
                <td className="text-xs">{humanize(o.type)}</td>
                <td className="tabular-nums">{tab === "history" ? formatCurrency(o.recovered_revenue) : `~${formatCurrency(o.potential_revenue)}`}</td>
                <td className="text-xs">{tab === "history" ? formatDate(o.closed_at) : formatDate(o.due_date)}</td>
                <td><Badge value={o.status === "won" ? "paid" : o.status === "in_progress" ? "contacted" : o.status === "lost" ? "lost" : o.status === "dismissed" ? "cancelled" : "pending"} className="capitalize" />{o.contact_count > 0 && <span className="ml-1 text-xs text-muted">×{o.contact_count}</span>}</td>
              </tr>))}</tbody>
          </table></div>
        )}
        {list.data && <Pager total={list.data.total} offset={offset} limit={50} onChange={setOffset} />}
      </Card>
      {s && <div className="mt-4"><InfoTip>{Object.entries(s.revenue.definitions).map(([k, v]) => <span key={k} className="mb-1 block"><strong className="text-fg">{humanize(k)}:</strong> {v}</span>)}</InfoTip></div>}

      <Modal open={!!open} onClose={() => setOpen(null)} title={detail.data?.opportunity.title ?? "Details"} wide>
        {detail.loading || !detail.data ? <Loading /> : (() => {
          const d = detail.data, o = d.opportunity, isOpen = ["open", "in_progress"].includes(o.status);
          return (
            <div className="space-y-4 text-sm">
              <p className="text-muted">{o.reason}</p>
              <div className="grid gap-3 sm:grid-cols-3">
                <div><p className="label">Who</p>{d.member?.name ?? d.lead?.name}<span className="block text-xs text-muted">{d.member?.phone ?? d.lead?.phone}</span></div>
                {d.membership && <div><p className="label">Membership</p>{d.membership.plan} · ends {formatDate(d.membership.end_date)}<span className="block text-xs text-muted">{formatCurrency(d.membership.amount)} · {d.membership.status}</span></div>}
                {d.payment && <div><p className="label">Payment</p>{formatCurrency(d.payment.amount)} · {humanize(d.payment.status)}<span className="block text-xs text-muted">{d.payment.failure_reason ?? (d.payment.due_date ? `due ${formatDate(d.payment.due_date)}` : "")}</span></div>}
              </div>
              <p className="text-xs text-muted">Reminders sent at: {o.milestones.length ? o.milestones.map((m) => (m === "after" ? "after expiry" : m === "0" ? "expiry day" : `${m} days before`)).join(", ") : "—"} · contacted {o.contact_count}× {o.last_contacted_at && `(last ${formatDateTime(o.last_contacted_at)})`}</p>
              {o.status === "won" && <Note tone="success">Recovered {formatCurrency(o.recovered_revenue)} - linked to a paid payment. {o.outcome}</Note>}
              {d.draft_message && isOpen && (
                <div className="rounded-lg bg-surface-2 p-3"><p className="label">Personalised message</p><p>{d.draft_message}</p>
                  <Button size="sm" variant="ghost" className="mt-2" onClick={() => { navigator.clipboard?.writeText(d.draft_message ?? ""); toast("Copied - send it via WhatsApp"); }}><Copy className="h-3.5 w-3.5" /> Copy</Button></div>
              )}
              {isOpen && <>
                <div className="flex gap-2"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Contact note, e.g. 'Will renew on Saturday'" />
                  <Button loading={busy === "contact"} onClick={() => run("contact", () => post(`/recovery/opportunities/${o.id}/contact`, { note: note || undefined }), "Contact recorded").then(() => { setNote(""); refresh(); })}>Log contact</Button></div>
                {d.payment && <Button variant="secondary" loading={busy === "link"} onClick={() => run("link", () => post<{ configured: boolean; url: string | null; detail?: string }>(`/recovery/opportunities/${o.id}/payment-link`)).then((r) => { if (!r) return; if (r.url) { navigator.clipboard?.writeText(r.url); toast("Payment link copied"); } else toast(r.detail ?? "Payment links unavailable", "error"); })}><Link2 className="h-4 w-4" /> Payment link</Button>}
                <div className="card space-y-2 p-3">
                  <p className="font-medium">Already paid with a payment you recorded?</p>
                  <p className="text-xs text-muted">Pick the payment so it counts as brought back. (Quicker: use the Paid button on Money → Due now.)</p>
                  <div className="flex gap-2"><Select value={payId} onChange={(e) => setPayId(e.target.value)} placeholder={d.creditable_payments.length ? "Choose paid payment" : "No uncredited paid payments"} options={d.creditable_payments.map((p) => ({ value: p.id, label: `${formatCurrency(p.amount)} · ${formatDate(p.paid_at)}` }))} />
                    <Button disabled={!payId} loading={busy === "pay"} onClick={() => run("pay", () => post(`/recovery/opportunities/${o.id}/record-payment`, { payment_id: payId }), "Counted as brought back").then(() => { setPayId(""); refresh(); })}>Link</Button></div>
                </div>
                <div className="card space-y-2 p-3">
                  <p className="font-medium">They won&apos;t pay or renew</p>
                  <div className="grid gap-2 sm:grid-cols-[140px_1fr_auto]">
                    <Select value={closeForm.status} onChange={(e) => setCloseForm({ ...closeForm, status: e.target.value })} options={[{ value: "lost", label: "Lost" }, { value: "dismissed", label: "Dismiss" }]} />
                    <Field label="" className="!m-0"><Input value={closeForm.outcome} onChange={(e) => setCloseForm({ ...closeForm, outcome: e.target.value })} placeholder="Reason (required)" /></Field>
                    <Button variant="danger" disabled={closeForm.outcome.length < 2} loading={busy === "close"} onClick={() => run("close", () => post(`/recovery/opportunities/${o.id}/close`, closeForm), "Closed").then(() => { setOpen(null); refresh(); })}>Close</Button>
                  </div>
                </div>
              </>}
            </div>
          );
        })()}
      </Modal>
    </FeatureGate>
  );
}
