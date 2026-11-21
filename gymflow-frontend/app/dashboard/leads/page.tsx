"use client";

import { Plus, Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { LeadDrawer, STAGES, stageLabel, type LeadRow } from "@/components/growth/LeadDrawer";
import { FeatureGate, Pager, useAction } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, Loading, Modal, PageHeader, Select } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, humanize } from "@/lib/utils";
import { post } from "@/services/api";
import type { Page } from "@/types";

const SOURCES = ["walk_in", "website", "website_chat", "whatsapp", "instagram", "google_business_profile", "referral", "qr_code",
  "paid_campaign", "corporate", "manual", "other"];

export default function LeadsPage() {
  const params = useSearchParams();
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [source, setSource] = useState(params.get("source") ?? "");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("newest");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "", email: "", source: "walk_in", fitness_interest: "", wants_trial: false, whatsapp_opt_in: false });
  const { busy, run } = useAction();
  const uncontacted = status === "uncontacted";
  const leads = useApi<Page<LeadRow>>("/crm/leads", { status: uncontacted ? "" : status, uncontacted, source, q, sort, offset, limit: 50 });

  return (
    <FeatureGate feature="lead_crm">
      <PageHeader title="Lead inbox" description="Every enquiry from every channel, de-duplicated and scored." actions={<Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Add lead</Button>} />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" /><Input className="pl-9" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} placeholder="Search name, phone or email" /></div>
        <Select className="sm:w-44" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} placeholder="All stages" options={[{ value: "uncontacted", label: "Uncontacted" }, ...STAGES.map((s) => ({ value: s, label: stageLabel(s) }))]} />
        <Select className="sm:w-48" value={source} onChange={(e) => { setSource(e.target.value); setOffset(0); }} placeholder="All sources" options={[...SOURCES, "seo_landing_page", "organic_search", "ai_search"]} />
        <Select className="sm:w-40" value={sort} onChange={(e) => setSort(e.target.value)} options={[{ value: "newest", label: "Newest" }, { value: "score", label: "Highest score" }, { value: "follow_up", label: "Next follow-up" }, { value: "oldest", label: "Oldest" }]} />
      </div>
      <Card>
        {leads.error && <div className="p-4"><ErrorNote message={leads.error} /></div>}
        {leads.loading ? <Loading /> : !leads.data?.items.length ? <EmptyState title="No leads match" description="Enquiries from your website, chat, WhatsApp and staff appear here." /> : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead><tr><th>Lead</th><th>Source</th><th>Stage</th><th>Score</th><th>Responded</th><th>Received</th></tr></thead>
              <tbody>
                {leads.data.items.map((l) => (
                  <tr key={l.id} className="cursor-pointer hover:bg-surface-2" onClick={() => setOpen(l.id)}>
                    <td><p className="font-medium">{l.name}</p><p className="text-xs text-muted">{l.phone ?? l.email}</p></td>
                    <td className="text-xs">{humanize(l.source)}<span className="block text-muted">{String(l.attribution?.method ?? "")}</span></td>
                    <td><Badge value={l.status} /></td>
                    <td className="tabular-nums">{l.score} <span className={`text-xs ${l.priority === "high" ? "text-danger" : "text-muted"}`}>{l.priority}</span></td>
                    <td className="text-xs">{l.first_response_at ? formatDateTime(l.first_response_at) : <span className="text-warning">Not yet</span>}</td>
                    <td className="text-xs text-muted">{formatDateTime(l.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {leads.data && <Pager total={leads.data.total} offset={offset} limit={50} onChange={setOffset} />}
      </Card>
      <LeadDrawer leadId={open} onClose={() => setOpen(null)} onChanged={leads.reload} />
      <Modal open={adding} onClose={() => setAdding(false)} title="Add a lead">
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); run("add", () => post<LeadRow>("/crm/leads", { ...form, email: form.email || undefined, fitness_interest: form.fitness_interest || undefined }), "Lead added - a follow-up task was created").then((r) => { if (r) { setAdding(false); leads.reload(); setOpen(r.id); } }); }}>
          <Field label="Name"><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Phone"><Input value={form.phone} inputMode="tel" onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
            <Field label="Email"><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Source"><Select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} options={SOURCES} /></Field>
            <Field label="Fitness interest"><Input value={form.fitness_interest} onChange={(e) => setForm({ ...form, fitness_interest: e.target.value })} placeholder="e.g. weight loss" /></Field>
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.wants_trial} onChange={(e) => setForm({ ...form, wants_trial: e.target.checked })} /> Wants a trial</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.whatsapp_opt_in} onChange={(e) => setForm({ ...form, whatsapp_opt_in: e.target.checked })} /> Agreed to WhatsApp messages</label>
          <p className="text-xs text-muted">Don&apos;t record health or medical details here.</p>
          <div className="flex justify-end"><Button type="submit" loading={busy === "add"} disabled={!form.phone && !form.email}>Save lead</Button></div>
        </form>
      </Modal>
    </FeatureGate>
  );
}
