"use client";

import { Play } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { FeatureGate, Kpi, Note, SourceBadge, useAction, useQueryTab } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, Loading, PageHeader, Tabs } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDateTime } from "@/lib/utils";
import { post } from "@/services/api";
import type { Audit } from "@/components/growth/types";

interface Perf { connected: boolean; message?: string; configured?: boolean; totals?: { clicks: number; impressions: number; ctr: number | null; avg_position: number | null }; queries?: { query: string; clicks: number; impressions: number; position: number | null }[]; pages?: { page: string; clicks: number; impressions: number }[]; last_sync_at?: string }
type Tab = "overview" | "audits" | "performance";

export default function SeoPage() {
  const [tab, setTab] = useQueryTab<Tab>("overview");
  const audits = useApi<Audit[]>("/seo/audits");
  const profile = useApi<{ website_url: string | null }>("/gym-profile");
  const perf = useApi<Perf>(tab === "performance" ? "/seo/performance" : null);
  const [url, setUrl] = useState("");
  const { busy, run } = useAction();
  useEffect(() => { if (profile.data?.website_url && !url) setUrl(profile.data.website_url); }, [profile.data, url]);
  const running = audits.data?.some((a) => a.status === "queued" || a.status === "running");
  useEffect(() => {
    if (!running) return;
    const t = setInterval(audits.reload, 2500);
    return () => clearInterval(t);
  }, [running, audits.reload]);
  const latest = audits.data?.find((a) => a.status === "completed");

  return (
    <FeatureGate feature="seo_audit">
      <PageHeader title="Website SEO" description="Audit your website for technical and on-page issues that keep local customers from finding you on Google." />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ value: "overview", label: "Overview" }, { value: "audits", label: "Audits" }, { value: "performance", label: "Search performance" }]} />

      {tab !== "performance" && (
        <Card className="mb-4">
          <form className="flex flex-col gap-2 p-4 sm:flex-row sm:items-end" onSubmit={(e) => { e.preventDefault(); run("audit", () => post<Audit>("/seo/audits", { url }), "Audit started").then(audits.reload); }}>
            <Field label="Website address" className="flex-1"><Input required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://yourgym.in" /></Field>
            <Button type="submit" loading={busy === "audit"} disabled={running}><Play className="h-4 w-4" /> {running ? "Audit running…" : "Run audit"}</Button>
          </form>
          <p className="px-4 pb-3 text-xs text-muted">GymFlow reads up to 25 pages, follows robots.txt, and only fetches public websites.</p>
          {audits.data?.filter((a) => a.status === "running" || a.status === "queued").map((a) => <p key={a.id} className="px-4 pb-3 text-xs text-brand">{a.summary.progress}</p>)}
        </Card>
      )}

      {tab === "overview" && (audits.loading ? <Loading /> : !latest ? <EmptyState title="No audit yet" description="Run your first audit above." /> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="SEO score" value={latest.score ?? "—"} hint="GymFlow checklist, not a Google score" href={`/dashboard/seo/audits/${latest.id}`} />
            <Kpi label="Critical + high issues" value={(latest.summary.counts?.critical ?? 0) + (latest.summary.counts?.high ?? 0)} tone="danger" href={`/dashboard/seo/audits/${latest.id}`} />
            <Kpi label="Pages audited" value={latest.pages_crawled} hint={latest.finished_at ? formatDateTime(latest.finished_at) : ""} />
            <Kpi label="Since last audit" value={latest.summary.comparison ? `${latest.summary.comparison.resolved_count} fixed` : "—"} hint={latest.summary.comparison ? `${latest.summary.comparison.new_count} new issues` : "Run again to compare"} />
          </div>
          {latest.data_source === "demo_simulated" && <Note tone="warning" className="mt-4">This audit is demo data. Run an audit on a real website to see live results.</Note>}
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {[["Keywords", "/dashboard/seo/keywords", "Local keyword ideas for your services and areas"], ["Landing pages", "/dashboard/seo/landing-pages", "Pages for the real areas you serve"], ["SEO reports", "/dashboard/reports?kind=seo", "Audit and progress reports"]].map(([t, h, d]) => (
              <Link key={h} href={h} className="card p-4 hover:border-brand/50"><p className="font-medium">{t}</p><p className="text-xs text-muted">{d}</p></Link>
            ))}
          </div>
        </>
      ))}

      {tab === "audits" && (
        <Card title="Audit history">
          {audits.error && <div className="p-4"><ErrorNote message={audits.error} /></div>}
          {!audits.data?.length ? <EmptyState title="No audits" /> : (
            <table className="table-base"><thead><tr><th>Website</th><th>When</th><th>Pages</th><th>Score</th><th>Status</th></tr></thead>
              <tbody>{audits.data.map((a) => (
                <tr key={a.id}><td><Link className="text-brand" href={`/dashboard/seo/audits/${a.id}`}>{a.url}</Link> <SourceBadge source={a.data_source} /></td><td className="text-xs">{formatDateTime(a.finished_at ?? a.created_at)}</td><td>{a.pages_crawled}</td><td className="tabular-nums">{a.score ?? "—"}</td><td><Badge value={a.status === "completed" ? "paid" : a.status === "failed" ? "failed" : "pending"} />{a.error && <span className="block text-xs text-danger">{a.error}</span>}</td></tr>
              ))}</tbody></table>
          )}
        </Card>
      )}

      {tab === "performance" && (perf.loading || !perf.data ? <Loading /> : !perf.data.connected ? (
        <Card><div className="p-6 text-center"><p className="font-medium">Google Search Console is not connected</p><p className="mx-auto mt-1 max-w-md text-sm text-muted">{perf.data.message}</p><Link href="/dashboard/integrations" className="mt-4 inline-block rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg">Connect Search Console</Link></div></Card>
      ) : (
        <>
          <div className="mb-3 flex items-center justify-between"><SourceBadge source="google_search_console" /><Button size="sm" variant="secondary" loading={busy === "sync"} onClick={() => run("sync", () => post("/seo/performance/sync"), "Synced from Search Console").then(perf.reload)}>Sync now</Button></div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Clicks" value={perf.data.totals?.clicks ?? 0} /><Kpi label="Impressions" value={perf.data.totals?.impressions ?? 0} />
            <Kpi label="CTR" value={perf.data.totals?.ctr != null ? `${(perf.data.totals.ctr * 100).toFixed(1)}%` : "—"} /><Kpi label="Avg position" value={perf.data.totals?.avg_position ?? "—"} />
          </div>
          <Card title="Top queries" className="mt-4"><table className="table-base"><thead><tr><th>Query</th><th>Clicks</th><th>Impressions</th><th>Position</th></tr></thead>
            <tbody>{perf.data.queries?.map((q) => <tr key={q.query}><td>{q.query}</td><td>{q.clicks}</td><td>{q.impressions}</td><td>{q.position}</td></tr>)}</tbody></table></Card>
        </>
      ))}
    </FeatureGate>
  );
}
