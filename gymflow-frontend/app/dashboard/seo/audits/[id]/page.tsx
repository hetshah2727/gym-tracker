"use client";

import { Copy, Sparkles } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";
import { Kpi, Note, SourceBadge, useAction, useToast } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, ErrorNote, Input, Loading, PageHeader, Select, Tabs } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, humanize } from "@/lib/utils";
import { patch, post } from "@/services/api";
import type { Audit } from "@/components/growth/types";

interface Finding { id: string; page_url: string | null; code: string; category: string; severity: string; title: string; evidence: string; recommendation: string; basis: string; status: string }
interface PageRow { id: string; url: string; status_code: number | null; title: string | null; meta_description: string | null; h1: string[]; word_count: number; load_ms: number | null; images: number; images_missing_alt: number; structured_data_types: string[]; issues: number }
interface Suggestion { id: string; target: string; field: string; current_value: string | null; suggested_value: string; reason: string; generated_by: string; warnings: string[]; status: string }
type Tab = "findings" | "pages" | "suggestions";
const SEV_TONE: Record<string, string> = { critical: "overdue", high: "failed", medium: "pending", low: "draft", info: "draft" };

export default function AuditDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const data = useApi<{ audit: Audit; findings: Finding[]; pages: PageRow[] }>(`/seo/audits/${id}`);
  const sugg = useApi<Suggestion[]>("/seo/suggestions", { status: "draft" });
  const [tab, setTab] = useState<Tab>("findings");
  const [sev, setSev] = useState("");
  const [cat, setCat] = useState("");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const { busy, run } = useAction();
  const toast = useToast();
  if (data.loading) return <Loading />;
  if (data.error || !data.data) return <ErrorNote message={data.error} />;
  const { audit, findings, pages } = data.data;
  const shown = findings.filter((f) => (!sev || f.severity === sev) && (!cat || f.category === cat));
  const pageSet = new Set(pages.map((p) => p.url));
  const mine = (sugg.data ?? []).filter((s) => pageSet.has(s.target));

  return (
    <>
      <PageHeader title={`Audit: ${audit.url}`} description={`${audit.pages_crawled} pages · ${formatDateTime(audit.finished_at ?? audit.created_at)}`}
        actions={<><SourceBadge source={audit.data_source} /><Link href="/dashboard/seo?tab=audits" className="text-sm text-brand">All audits</Link></>} />
      {audit.data_source === "demo_simulated" && <Note tone="warning" className="mb-4">Demo data - findings were seeded for the demo, not crawled.</Note>}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label="Score" value={audit.score ?? "—"} hint="GymFlow checklist" />
        {["critical", "high", "medium", "low"].map((s) => <Kpi key={s} label={humanize(s)} value={audit.summary.counts?.[s] ?? 0} tone={s === "critical" || s === "high" ? "danger" : undefined} />)}
      </div>
      <p className="mt-2 text-xs text-muted">{(audit.summary as { score_method?: string }).score_method}</p>
      <div className="mt-4"><Tabs<Tab> value={tab} onChange={setTab} tabs={[{ value: "findings", label: `Findings (${findings.length})` }, { value: "pages", label: `Pages (${pages.length})` }, { value: "suggestions", label: `Suggestions (${mine.length})` }]} /></div>

      {tab === "findings" && (
        <Card>
          <div className="flex gap-2 border-b border-border p-3">
            <Select className="w-40" value={sev} onChange={(e) => setSev(e.target.value)} placeholder="All severities" options={["critical", "high", "medium", "low", "info"]} />
            <Select className="w-40" value={cat} onChange={(e) => setCat(e.target.value)} placeholder="All categories" options={["technical", "on_page", "content", "local"]} />
          </div>
          {!shown.length ? <EmptyState title="No findings" /> : <ul className="divide-y divide-border/60">{shown.map((f) => (
            <li key={f.id} className="px-4 py-3 text-sm">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div><p className="font-medium">{f.title} <Badge value={SEV_TONE[f.severity]} className="ml-1 !normal-case" /> <span className="text-xs text-muted">{humanize(f.severity)} · {humanize(f.category)}</span></p>
                  {f.page_url && <p className="text-xs text-muted">{f.page_url}</p>}</div>
                <Select className="w-32 py-1 text-xs" value={f.status} onChange={(e) => run(f.id, () => patch(`/seo/findings/${f.id}`, { status: e.target.value }), "Updated").then(data.reload)} options={["open", "resolved", "ignored"]} />
              </div>
              <p className="mt-1 text-xs"><span className="text-muted">Observed:</span> {f.evidence}</p>
              <p className="mt-0.5 text-xs"><span className="text-muted">Fix:</span> {f.recommendation}</p>
            </li>))}</ul>}
        </Card>
      )}

      {tab === "pages" && (
        <Card><div className="overflow-x-auto"><table className="table-base">
          <thead><tr><th>Page</th><th>Status</th><th>Title</th><th>Words</th><th>Alt missing</th><th>Schema</th><th>Issues</th></tr></thead>
          <tbody>{pages.map((p) => <tr key={p.id}><td className="max-w-[220px] truncate text-xs">{p.url}</td><td>{p.status_code}</td><td className="max-w-[220px] truncate text-xs">{p.title ?? <span className="text-danger">missing</span>}</td><td>{p.word_count}</td><td>{p.images_missing_alt}/{p.images}</td><td className="text-xs">{p.structured_data_types.join(", ") || "—"}</td><td>{p.issues}</td></tr>)}</tbody>
        </table></div></Card>
      )}

      {tab === "suggestions" && (
        <Card title="On-page suggestions" actions={<Button size="sm" loading={busy === "gen"} onClick={() => run("gen", () => post<Suggestion[]>(`/seo/audits/${id}/suggestions`), (r) => `${r.length} suggestions drafted`).then(sugg.reload)}><Sparkles className="h-4 w-4" /> Generate</Button>}>
          <div className="p-4 pb-0"><Note>Nothing changes on your website until you approve. For websites not built with GymFlow you get copy-ready text.</Note></div>
          {!mine.length ? <EmptyState title="No pending suggestions" description="Generate suggestions for pages with title, description, H1 or alt-text issues." /> : <ul className="divide-y divide-border/60">{mine.map((s) => (
            <li key={s.id} className="space-y-2 px-4 py-3 text-sm">
              <p className="text-xs text-muted">{s.target} · <strong className="text-fg">{humanize(s.field.split(":")[0])}</strong> <SourceBadge source={s.generated_by} /></p>
              <div className="grid gap-2 sm:grid-cols-2">
                <div><p className="label">Current</p><p className="rounded-lg bg-surface-2 p-2 text-xs">{s.current_value ?? <em className="text-muted">empty</em>}</p></div>
                <div><p className="label">Suggested</p><Input value={edits[s.id] ?? s.suggested_value} onChange={(e) => setEdits({ ...edits, [s.id]: e.target.value })} /></div>
              </div>
              <p className="text-xs text-muted">{s.reason}</p>
              {s.warnings.length > 0 && <Note tone="warning">{s.warnings.join("; ")}</Note>}
              <div className="flex gap-2">
                <Button size="sm" loading={busy === s.id} onClick={() => run(s.id, () => post<{ copy_ready: string | null; applied_to_gymflow_site: boolean; instructions: string | null }>(`/seo/suggestions/${s.id}/decide`, { approve: true, edited_value: edits[s.id] })).then((r) => {
                  if (!r) return;
                  if (r.copy_ready) { navigator.clipboard?.writeText(r.copy_ready); toast("Approved and copied. " + (r.instructions ?? "")); } else toast("Applied to your GymFlow site");
                  sugg.reload();
                })}><Copy className="h-3.5 w-3.5" /> Approve</Button>
                <Button size="sm" variant="ghost" onClick={() => run("rej" + s.id, () => post(`/seo/suggestions/${s.id}/decide`, { approve: false }), "Rejected").then(sugg.reload)}>Reject</Button>
              </div>
            </li>))}</ul>}
        </Card>
      )}
    </>
  );
}
