"use client";

import { FileBarChart, Printer } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useAction } from "@/components/shared/growth";
import { Button, Card, EmptyState, Loading, PageHeader, Select } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, formatDateTime, humanize } from "@/lib/utils";
import { post } from "@/services/api";

interface ReportRow { id: string; kind: string; title: string; generated_by: string; created_at: string }
interface Report { id: string; title: string; kind: string; content: Record<string, unknown>; created_at: string }
const SEO_KINDS = ["seo_audit", "seo_progress", "monthly_seo"];
const MONEY = /(revenue|collected|recovered|outstanding|overdue|potential|forecast|amount|value)/;

function Value({ k, v }: { k: string; v: unknown }): React.ReactElement {
  if (v === null || v === undefined) return <span className="text-muted">—</span>;
  if (typeof v === "number") return <span className="tabular-nums">{MONEY.test(k) ? formatCurrency(v) : v.toLocaleString("en-IN")}</span>;
  if (typeof v === "string" || typeof v === "boolean") return <span>{String(v)}</span>;
  if (Array.isArray(v)) {
    if (!v.length) return <span className="text-muted">none</span>;
    return <ul className="list-disc space-y-1 pl-5">{v.slice(0, 15).map((x, i) => <li key={i}>{typeof x === "object" && x ? ((x as Record<string, unknown>).title as string) ?? Object.entries(x as object).filter(([, y]) => typeof y !== "object").map(([a, b]) => `${humanize(a)}: ${b}`).join(" · ") : String(x)}</li>)}</ul>;
  }
  return <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-2">{Object.entries(v as object).filter(([key]) => key !== "definitions").map(([a, b]) => <div key={a} className="flex flex-col"><dt className="text-xs text-muted">{humanize(a)}</dt><dd className="text-sm"><Value k={a} v={b} /></dd></div>)}</dl>;
}

export default function ReportsPage() {
  const params = useSearchParams();
  const seoOnly = params.get("kind") === "seo";
  const kinds = useApi<Record<string, string>>("/growth/reports/kinds");
  const list = useApi<ReportRow[]>("/growth/reports");
  const [kind, setKind] = useState(seoOnly ? "seo_audit" : "weekly_revenue");
  const [open, setOpen] = useState<string | null>(null);
  const report = useApi<Report>(open ? `/growth/reports/${open}` : null);
  const { busy, run } = useAction();
  const rows = (list.data ?? []).filter((r) => !seoOnly || SEO_KINDS.includes(r.kind));
  const options = Object.entries(kinds.data ?? {}).filter(([k]) => !seoOnly || SEO_KINDS.includes(k)).map(([value, label]) => ({ value, label }));

  return (
    <>
      <PageHeader title={seoOnly ? "SEO reports" : "Growth reports"} description="Snapshots of your real numbers. Generated daily by the workflow, or whenever you need one."
        actions={<><Select className="w-56" value={kind} onChange={(e) => setKind(e.target.value)} options={options} />
          <Button loading={busy === "gen"} onClick={() => run("gen", () => post<{ id: string }>("/growth/reports", { kind }), "Report generated").then((r) => { if (r) { list.reload(); setOpen(r.id); } })}><FileBarChart className="h-4 w-4" /> Generate</Button></>} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Saved reports">{list.loading ? <Loading /> : !rows.length ? <EmptyState title="No reports yet" /> : <ul className="divide-y divide-border/60">{rows.map((r) => (
          <li key={r.id}><button onClick={() => setOpen(r.id)} className={`w-full px-4 py-3 text-left text-sm hover:bg-surface-2 ${open === r.id ? "bg-surface-2" : ""}`}><p className="font-medium">{r.title}</p><p className="text-xs text-muted">{formatDateTime(r.created_at)} · {r.generated_by}</p></button></li>))}</ul>}</Card>
        <Card title={report.data?.title ?? "Report"} className="lg:col-span-2" actions={report.data && <Button size="sm" variant="ghost" onClick={() => window.print()}><Printer className="h-4 w-4" /> Print</Button>}>
          <div className="p-4">{!open ? <EmptyState title="Choose a report" /> : report.loading || !report.data ? <Loading /> : (
            <div className="space-y-5">{Object.entries(report.data.content).map(([k, v]) => <section key={k}><h3 className="mb-2 text-sm font-semibold">{humanize(k)}</h3><Value k={k} v={v} /></section>)}</div>
          )}</div>
        </Card>
      </div>
    </>
  );
}
