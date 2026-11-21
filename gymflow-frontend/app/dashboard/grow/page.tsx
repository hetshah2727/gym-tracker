"use client";

import { ArrowRight, Bot, Globe, MapPin, Sparkles, Star } from "lucide-react";
import Link from "next/link";
import type { Recommendation } from "@/components/growth/Lists";
import { HBars } from "@/components/charts/Charts";
import { useEntitlements } from "@/components/shared/growth";
import { Card, EmptyState, ErrorNote, InfoTip, Skeleton } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { cn, humanize } from "@/lib/utils";

interface Dashboard {
  acquisition: {
    website_seo: { score: number | null; serious_issues: number; audit_id: string | null };
    google_business_profile: { connection: string; completeness: number | null; rating: number | null; review_count: number | null; reviews_awaiting_reply: number };
    ai_search_readiness: { score: number | null; gaps: number | null };
    website_enquiries: number;
    lead_sources: Record<string, number>;
  };
  recommendations: Recommendation[];
}

const GROWTH_MODULES = new Set(["seo", "local", "ai_search"]);

function scoreTone(v: number | null) {
  return v == null ? "text-muted" : v >= 75 ? "text-money" : v >= 50 ? "text-warning" : "text-danger";
}

function Ring({ value }: { value: number | null }) {
  const pct = value ?? 0;
  const r = 52, c = 2 * Math.PI * r;
  return (
    <svg viewBox="0 0 120 120" className="h-32 w-32 shrink-0" role="img" aria-label={value == null ? "Not checked yet" : `${value} out of 100`}>
      <circle cx="60" cy="60" r={r} fill="none" stroke="currentColor" strokeWidth="10" className="text-surface-2" />
      <circle cx="60" cy="60" r={r} fill="none" stroke="currentColor" strokeWidth="10" strokeLinecap="round"
        strokeDasharray={`${(pct / 100) * c} ${c}`} transform="rotate(-90 60 60)" className={scoreTone(value)} />
      <text x="60" y="58" textAnchor="middle" className="fill-fg font-display text-[30px] font-extrabold">{value ?? "–"}</text>
      <text x="60" y="80" textAnchor="middle" className="fill-muted text-[11px]">out of 100</text>
    </svg>
  );
}

export default function GrowPage() {
  const { data: d, error, loading } = useApi<Dashboard>("/growth/dashboard");
  const { ent } = useEntitlements();
  if (error) return <ErrorNote message={error} />;
  const a = d?.acquisition;
  const parts = a ? [a.website_seo.score, a.google_business_profile.completeness, a.ai_search_readiness.score].filter((v): v is number => v != null) : [];
  const score = parts.length ? Math.round(parts.reduce((x, y) => x + y, 0) / parts.length) : null;
  const todo = (d?.recommendations ?? []).filter((r) => GROWTH_MODULES.has(r.module));
  const gbp = a?.google_business_profile;
  const locked = (f: string) => ent?.features[f] === false;

  const tiles = a ? [
    { href: "/dashboard/local", icon: MapPin, title: "Google Maps listing", feature: "local_seo",
      value: gbp?.completeness != null ? `${gbp.completeness}% complete` : gbp?.connection === "connected" ? "Connected" : "Not connected",
      detail: gbp?.rating ? `${gbp.rating}★ from ${gbp.review_count} reviews` : "Where most new members find you" },
    { href: "/dashboard/local/reviews", icon: Star, title: "Google reviews", feature: "local_seo",
      value: gbp?.reviews_awaiting_reply ? `${gbp.reviews_awaiting_reply} to answer` : "All answered",
      detail: "Replies help you rank higher on Maps" },
    { href: "/dashboard/seo", icon: Globe, title: "Website health", feature: "seo_audit",
      value: a.website_seo.score != null ? `${a.website_seo.score}/100` : "Not checked",
      detail: a.website_seo.serious_issues ? `${a.website_seo.serious_issues} problems to fix` : "How Google sees your website" },
    { href: "/dashboard/ai-search", icon: Sparkles, title: "ChatGPT & AI search", feature: "ai_search_readiness",
      value: a.ai_search_readiness.score != null ? `${a.ai_search_readiness.score}/100` : "Not checked",
      detail: "When people ask AI for a gym near them" },
    { href: "/dashboard/sales-agent", icon: Bot, title: "AI receptionist", feature: "ai_sales_agent",
      value: `${a.website_enquiries} enquiries`, detail: "Replies to enquiries 24×7 and books trials" },
  ] : [];
  const sources = a ? Object.entries(a.lead_sources).sort((x, y) => y[1] - x[1]).map(([k, v]) => ({ label: humanize(k), value: v })) : [];

  return (
    <>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold tracking-tight sm:text-[1.7rem]">Get more people through the door</h1>
        <p className="mt-1 text-sm text-muted">How easily people near you can find your gym on Google, Maps and AI apps – and what to fix first.</p>
      </div>

      {loading || !a ? <Skeleton className="h-48" /> : (
        <Card className="flex flex-col items-center gap-6 p-6 sm:flex-row">
          <Ring value={score} />
          <div className="flex-1">
            <p className="text-sm text-muted">Your online score</p>
            <p className="font-display text-xl font-bold">
              {score == null ? "Run your first check to see your score" : score >= 75 ? "People can find you easily" : score >= 50 ? "You're visible, with easy wins left" : "Many people nearby can't find you yet"}
            </p>
            <p className="mt-1 text-sm text-muted">{a.website_enquiries} enquiries came from Google, Maps, your website and chat this month.</p>
            <div className="mt-3"><InfoTip>The average of your website health, Google Maps listing completeness and AI-search checklist – only the parts you&apos;ve checked. GymFlow never guesses search numbers.</InfoTip></div>
          </div>
        </Card>
      )}

      <Card title="Fix these next" className="mt-6">
        {loading ? <div className="space-y-2 p-4"><Skeleton className="h-12" /><Skeleton className="h-12" /></div> : todo.length === 0 ? (
          <EmptyState title="Nothing urgent" description="Your listing and website look good. GymFlow checks again regularly." />
        ) : (
          <ol className="divide-y divide-border/60">
            {todo.map((r, i) => (
              <li key={r.id}>
                <Link href={r.href} className="flex items-center gap-4 px-5 py-4 hover:bg-surface-2">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/10 font-display text-sm font-bold text-brand">{i + 1}</span>
                  <span className="min-w-0 flex-1"><span className="block font-semibold">{r.title}</span><span className="block text-xs text-muted">{r.detail}</span></span>
                  <span className="hidden items-center gap-1 text-sm font-semibold text-brand sm:flex">Do it <ArrowRight className="h-4 w-4" /></span>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </Card>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map((t) => (
          <Link key={t.href} href={locked(t.feature) ? "/dashboard/plan" : t.href} className="card group p-5 transition hover:shadow-soft">
            <div className="flex items-center justify-between">
              <t.icon className="h-5 w-5 text-brand" />
              {locked(t.feature) && <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-semibold text-muted">Upgrade</span>}
            </div>
            <p className="mt-3 text-sm text-muted">{t.title}</p>
            <p className={cn("font-display text-lg font-bold")}>{t.value}</p>
            <p className="mt-0.5 text-xs text-muted">{t.detail}</p>
          </Link>
        ))}
      </div>

      {sources.length > 0 && (
        <Card title="Where enquiries came from this month" className="mt-6">
          <div className="p-5"><HBars data={sources} valueLabel="Enquiries" /></div>
        </Card>
      )}
    </>
  );
}
