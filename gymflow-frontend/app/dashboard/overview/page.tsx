"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { HBars, RevenueBars } from "@/components/charts/Charts";
import { ActionList, RecommendationList, type Action, type Recommendation } from "@/components/growth/Lists";
import { Kpi, Note, SourceBadge, percent } from "@/components/shared/growth";
import { Button, Card, EmptyState, ErrorNote, Input, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, formatDate, humanize } from "@/lib/utils";

interface Dashboard {
  period: { start: string; end: string };
  gym: { name: string; currency: string; is_demo: boolean };
  business: Record<string, number> & { currency: string };
  acquisition: {
    website_seo: { score: number | null; audited_at: string | null; serious_issues: number; data_source: string | null; audit_id: string | null };
    google_business_profile: { connection: string; completeness: number | null; snapshot_source: string | null; rating: number | null; review_count: number | null; reviews_awaiting_reply: number };
    ai_search_readiness: { score: number | null; gaps: number | null };
    search_console: { connection?: string; clicks?: number; impressions?: number };
    website_enquiries: number;
    lead_sources: Record<string, number>;
  };
  sales: { new_leads: number; total_enquiries: number; contacted: number; uncontacted: number; overdue_follow_ups: number; upcoming_trials: number; trial_conversion: number | null; avg_first_response_minutes: number | null };
  recovery: { open_opportunities: number; expiring_7d: number; pending_payments: number; failed_payments: number; potential_value: number; recovered_this_month: number };
  revenue_series: { month: string; collected: number; recovered: number }[];
  actions: Action[];
  recommendations: Recommendation[];
}

const PROMPTS = ["Analyze my gym this month", "How can I get more local enquiries?", "Show my SEO issues",
  "Which leads should I contact today?", "Which memberships expire this week?", "How much revenue is outstanding?",
  "Which marketing sources generate paying members?", "Give me a seven-day growth plan"];

export default function OverviewPage() {
  const { data: d, error, loading } = useApi<Dashboard>("/growth/dashboard");
  const router = useRouter();
  const [ask, setAsk] = useState("");
  if (loading) return <Loading />;
  if (error || !d) return <ErrorNote message={error} />;
  const b = d.business, a = d.acquisition, s = d.sales, r = d.recovery, cur = d.gym.currency;
  const go = (q: string) => router.push(`/dashboard/assistant?q=${encodeURIComponent(q)}`);
  const sources = Object.entries(a.lead_sources).sort((x, y) => y[1] - x[1]).map(([k, v]) => ({ label: humanize(k), value: v }));

  return (
    <>
      <PageHeader title={`Good to see you, ${d.gym.name}`} description={`This month so far (${formatDate(d.period.start)} – ${formatDate(d.period.end)}). Every number below comes from your records.`}
        actions={d.gym.is_demo ? <SourceBadge source="demo_simulated" /> : undefined} />

      <section aria-label="Business overview" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Active members" value={b.active_members} hint={`${b.inactive_or_expired_members} inactive or expired`} href="/dashboard/members" />
        <Kpi label="New leads" value={b.new_leads} hint={`${s.uncontacted} still uncontacted`} href="/dashboard/leads" tone={s.uncontacted ? "warning" : undefined} />
        <Kpi label="Trials scheduled" value={b.trials_scheduled} hint="Upcoming booked trials" href="/dashboard/trials" />
        <Kpi label="New memberships" value={b.new_memberships} hint="Including renewals" href="/dashboard/memberships" />
        <Kpi label="Membership revenue" value={formatCurrency(b.membership_revenue, cur)} hint="Collected (paid) this month" href="/dashboard/revenue" tone="brand" />
        <Kpi label="Outstanding payments" value={formatCurrency(b.outstanding, cur)} hint={`${b.outstanding_count} unpaid records`} href="/dashboard/recovery?tab=outstanding" tone={b.outstanding ? "danger" : undefined} />
        <Kpi label="Upcoming renewals" value={b.upcoming_renewals_30d} hint="Ending in the next 30 days" href="/dashboard/recovery" />
        <Kpi label="Recovered revenue" value={formatCurrency(b.recovered_revenue, cur)} hint="Backed by paid payments" href="/dashboard/recovery?tab=history" tone="brand" />
      </section>

      <div className="mt-6 grid gap-4 lg:grid-cols-5">
        <Card title="Today's recommended actions" className="lg:col-span-3" actions={<Link href="/dashboard/actions" className="text-xs text-brand">All actions</Link>}>
          <ActionList actions={d.actions.slice(0, 7)} />
        </Card>
        <Card title="AI business analyst" className="lg:col-span-2">
          <div className="p-4">
            <form onSubmit={(e) => { e.preventDefault(); if (ask.trim()) go(ask); }} className="flex gap-2">
              <Input value={ask} onChange={(e) => setAsk(e.target.value)} placeholder="Ask about your gym…" aria-label="Ask the business analyst" />
              <Button type="submit" aria-label="Ask"><Sparkles className="h-4 w-4" /></Button>
            </form>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {PROMPTS.map((p) => (
                <button key={p} onClick={() => go(p)} className="rounded-full border border-border px-2.5 py-1 text-xs text-muted hover:border-brand/50 hover:text-fg">{p}</button>
              ))}
            </div>
          </div>
        </Card>
      </div>

      <h2 className="mb-3 mt-8 text-sm font-semibold uppercase tracking-wide text-muted">Acquisition</h2>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Website SEO score" value={a.website_seo.score ?? "—"} hint={a.website_seo.audited_at ? <>{a.website_seo.serious_issues} serious issues · {a.website_seo.data_source === "demo_simulated" ? "demo data" : formatDate(a.website_seo.audited_at)}</> : "No audit yet"} href="/dashboard/seo" />
        <Kpi label="Google Business Profile" value={a.google_business_profile.completeness != null ? `${a.google_business_profile.completeness}%` : humanize(a.google_business_profile.connection)}
          hint={a.google_business_profile.completeness != null ? `Completeness · ${a.google_business_profile.connection === "connected" ? "connected" : `${humanize(a.google_business_profile.snapshot_source)} data`}` : "Connect to audit your profile"} href="/dashboard/local" />
        <Kpi label="AI-search readiness" value={a.ai_search_readiness.score ?? "—"} hint={a.ai_search_readiness.score != null ? `${a.ai_search_readiness.gaps} gaps · GymFlow checklist` : "Not checked yet"} href="/dashboard/ai-search" />
        <Kpi label="Website enquiries" value={a.website_enquiries} hint="Website, chat, landing pages, search, Maps link" href="/dashboard/lead-sources" />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <Card title="Lead sources this month" className="lg:col-span-2">
          <div className="p-4">{sources.length ? <HBars data={sources} valueLabel="Enquiries" /> : <EmptyState title="No enquiries yet" />}</div>
        </Card>
        <Card title="Revenue: collected vs recovered (6 months)" className="lg:col-span-3">
          <div className="p-4"><RevenueBars data={d.revenue_series} /></div>
        </Card>
      </div>
      {a.search_console.connection && a.search_console.connection !== "connected" && (
        <Note className="mt-4">Search Console is not connected, so clicks and impressions are not shown. <Link href="/dashboard/integrations" className="underline">Connect it</Link> – GymFlow never estimates these numbers.</Note>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Sales</h2>
          <div className="grid grid-cols-2 gap-3">
            <Kpi label="Contacted" value={s.contacted} hint={`of ${s.total_enquiries} enquiries`} href="/dashboard/pipeline" />
            <Kpi label="Uncontacted" value={s.uncontacted} href="/dashboard/leads?status=new" tone={s.uncontacted ? "warning" : undefined} />
            <Kpi label="Overdue follow-ups" value={s.overdue_follow_ups} href="/dashboard/follow-ups?due=overdue" tone={s.overdue_follow_ups ? "danger" : undefined} />
            <Kpi label="Trial → member" value={percent(s.trial_conversion)} hint={`${s.upcoming_trials} upcoming trials`} href="/dashboard/trials?tab=conversion" />
          </div>
        </section>
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Recovery</h2>
          <div className="grid grid-cols-2 gap-3">
            <Kpi label="Expiring in 7 days" value={r.expiring_7d} href="/dashboard/recovery" />
            <Kpi label="Pending payments" value={r.pending_payments} href="/dashboard/recovery?tab=outstanding" />
            <Kpi label="Failed payments" value={r.failed_payments} href="/dashboard/recovery?tab=failed" tone={r.failed_payments ? "danger" : undefined} />
            <Kpi label="Open opportunities" value={r.open_opportunities} hint={`~${formatCurrency(r.potential_value, cur)} potential (estimate)`} href="/dashboard/recovery?tab=opportunities" />
          </div>
        </section>
      </div>

      <Card title="Growth recommendations" className="mt-6" actions={<Link href="/dashboard/assistant" className="text-xs text-brand">Ask the analyst</Link>}>
        <RecommendationList items={d.recommendations} currency={cur} />
      </Card>
    </>
  );
}
