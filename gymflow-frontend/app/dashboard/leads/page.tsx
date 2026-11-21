"use client";

import { MessageCircle, Plus, Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { LeadDrawer, STAGES, heat, stageLabel, type LeadRow } from "@/components/growth/LeadDrawer";
import { FeatureGate, Pager, useAction } from "@/components/shared/growth";
import { Button, Card, EmptyState, ErrorNote, Field, Input, Loading, Modal, PageHeader, Select } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, humanize, whatsappLink } from "@/lib/utils";
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
  useEffect(() => { if (params.get("new") === "1") setAdding(true); }, [params]);
  const uncontacted = status === "uncontacted";
  const leads = useApi<Page<LeadRow>>("/crm/leads", { status: uncontacted ? "" : status, uncontacted, source, q, sort, offset, limit: 50 });

  return (
    <FeatureGate feature="lead_crm">
      <PageHeader title="Enquiries" description="Everyone who asked about joining – from WhatsApp, Google, your website, Instagram or walk-ins." actions={<Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Add enquiry</Button>} />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" /><Input className="pl-9" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} placeholder="Search name, phone or email" /></div>
        <Select className="sm:w-44" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} placeholder="All stages" options={[{ value: "uncontacted", label: "Not replied yet" }, ...STAGES.map((s) => ({ value: s, label: stageLabel(s) }))]} />
        <Select className="sm:w-48" value={source} onChange={(e) => { setSource(e.target.value); setOffset(0); }} placeholder="All sources" options={[...SOURCES, "seo_landing_page", "organic_search", "ai_search"]} />
        <Select className="sm:w-40" value={sort} onChange={(e) => setSort(e.target.value)} options={[{ value: "newest", label: "Newest" }, { value: "score", label: "Hottest first" }, { value: "follow_up", label: "Next follow-up" }, { value: "oldest", label: "Oldest" }]} />
      </div>
      <Card>
        {leads.error && <div className="p-4"><ErrorNote message={leads.error} /></div>}
        {leads.loading ? <Loading /> : !leads.data?.items.length ? <EmptyState title="No enquiries here" description="Enquiries from your website, Google, WhatsApp and walk-ins show up here." /> : (
          <ul className="divide-y divide-border/60">
            {leads.data.items.map((l) => {
              const h = heat(l.score);
              const waiting = !l.first_response_at && l.status === "new";
              return (
                <li key={l.id} className="flex items-center gap-3 px-4 py-3.5 hover:bg-surface-2/60 sm:px-5">
                  <button className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={() => setOpen(l.id)}>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ${h.tone}`}>{h.label}</span>
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">{l.name}</span>
                      <span className="block truncate text-xs text-muted">
                        {humanize(l.source)} · {formatDateTime(l.created_at)}
                        {l.fitness_interest && <> · {l.fitness_interest}</>}
                      </span>
                    </span>
                  </button>
                  <span className={`hidden whitespace-nowrap text-xs font-medium sm:block ${waiting ? "text-warning" : "text-muted"}`}>{stageLabel(l.status)}</span>
                  {l.phone && (
                    <a href={whatsappLink(l.phone)} target="_blank" rel="noreferrer" className="rounded-xl border border-border p-2 hover:bg-surface-2" aria-label={`WhatsApp ${l.name}`}>
                      <MessageCircle className="h-4 w-4 text-money" />
                    </a>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {leads.data && <Pager total={leads.data.total} offset={offset} limit={50} onChange={setOffset} />}
      </Card>
      <LeadDrawer leadId={open} onClose={() => setOpen(null)} onChanged={leads.reload} />
      <Modal open={adding} onClose={() => setAdding(false)} title="Add an enquiry">
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); run("add", () => post<LeadRow>("/crm/leads", { ...form, email: form.email || undefined, fitness_interest: form.fitness_interest || undefined }), "Enquiry saved – we added a reminder to follow up").then((r) => { if (r) { setAdding(false); leads.reload(); setOpen(r.id); } }); }}>
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
          <div className="flex justify-end"><Button type="submit" loading={busy === "add"} disabled={!form.phone && !form.email}>Save enquiry</Button></div>
        </form>
      </Modal>
    </FeatureGate>
  );
}
