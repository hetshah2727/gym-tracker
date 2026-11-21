"use client";

import { Copy, Download, ImageIcon, RefreshCcw, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { FeatureGate, Kpi, Note, SourceBadge, useAction, useQueryTab, useToast } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, Field, Input, Loading, PageHeader, Select, Tabs, Textarea } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, humanize } from "@/lib/utils";
import { post } from "@/services/api";

interface Finding { code: string; issue: string; priority: string; explanation: string; recommendation: string; suggested_correction: string | null }
interface Overview {
  connection: string; configured: boolean; completeness: number | null; rating: number | null; review_count: number | null; reviews_awaiting_reply: number;
  latest_audit: { source: string; completeness: number; findings: Finding[]; data: Record<string, unknown>; fetched_at: string } | null;
  reviews: { total_recorded: number; average_recorded_rating: number | null; sentiment: Record<string, number>; by_month: Record<string, number> };
  website_enquiries_this_month: number; gbp_tracked_enquiries_this_month: number; engagement_metrics: string;
}
type Tab = "overview" | "profile" | "posts";

export default function LocalPage() {
  const [tab, setTab] = useQueryTab<Tab>("overview");
  const o = useApi<Overview>("/local/overview");
  const [manual, setManual] = useState({ name: "", primary_category: "Gym", description: "", address: "", phone: "", website: "", services: "", review_count: "", rating: "" });
  const [post_, setPost] = useState({ kind: "update", details: "" });
  const [draft, setDraft] = useState<{ text: string; call_to_action: string; generated_by: string; warnings: string[] } | null>(null);
  const [picture, setPicture] = useState<string | null>(null);
  const { busy, run } = useAction();
  const toast = useToast();
  const d = o.data;
  const connected = d?.connection === "connected";

  return (
    <FeatureGate feature="local_seo">
      <PageHeader title="Google Maps SEO" description="Business Profile quality, reviews and local enquiries. GymFlow never claims map-pack rankings it can't measure." />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ value: "overview", label: "Local visibility" }, { value: "profile", label: "Business profile audit" }, { value: "posts", label: "Profile posts" }]} />
      {o.loading || !d ? <Loading /> : <>
        {!connected && <Note className="mb-4">Google Business Profile is {humanize(d.connection).toLowerCase()}. {d.configured ? <Link className="underline" href="/dashboard/integrations">Connect it</Link> : "Your GymFlow administrator must add Google OAuth credentials first."} - until then you can audit by entering your profile details by hand.</Note>}

        {tab === "overview" && <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Profile completeness" value={d.latest_audit ? `${d.latest_audit.completeness}%` : "—"} hint={d.latest_audit ? <SourceBadge source={d.latest_audit.source} /> : "Run a profile audit"} />
            <Kpi label="Rating" value={d.rating ?? d.reviews.average_recorded_rating ?? "—"} hint={d.review_count != null ? `${d.review_count} reviews on profile` : `${d.reviews.total_recorded} reviews recorded`} />
            <Kpi label="Reviews awaiting reply" value={d.reviews_awaiting_reply} href="/dashboard/local/reviews" tone={d.reviews_awaiting_reply ? "warning" : undefined} />
            <Kpi label="Enquiries via profile link" value={d.gbp_tracked_enquiries_this_month} hint="Tracked links only, this month" href="/dashboard/lead-sources" />
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Top profile fixes">
              {!d.latest_audit?.findings.length ? <EmptyState title="No audit findings" /> : <ul className="divide-y divide-border/60">{d.latest_audit.findings.slice(0, 6).map((f) => (
                <li key={f.code} className="px-4 py-3 text-sm"><p className="font-medium">{f.issue} <Badge value={f.priority === "high" ? "overdue" : "pending"} className="ml-1" /></p><p className="text-xs text-muted">{f.recommendation}</p></li>))}</ul>}
            </Card>
            <Card title="Review sentiment (recorded reviews)">
              <div className="grid grid-cols-3 gap-3 p-4">{(["positive", "neutral", "negative"] as const).map((k) => <Kpi key={k} label={humanize(k)} value={d.reviews.sentiment[k] ?? 0} />)}</div>
              <p className="px-4 pb-4 text-xs text-muted">{d.engagement_metrics}</p>
            </Card>
          </div>
        </>}

        {tab === "profile" && <>
          <Card title="Run an audit" className="mb-4">
            <div className="space-y-3 p-4">
              {connected && <Button loading={busy === "sync"} onClick={() => run("sync", () => post("/local/profile-audit/sync"), "Synced from Google and audited").then(o.reload)}><RefreshCcw className="h-4 w-4" /> Sync from Google & audit</Button>}
              <details className="rounded-lg border border-border p-3" open={!connected}>
                <summary className="cursor-pointer text-sm font-medium">Audit by entering your profile details</summary>
                <form className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); run("manual", () => post("/local/profile-audit/manual", { ...manual, services: manual.services.split(",").map((s) => s.trim()).filter(Boolean), review_count: manual.review_count ? Number(manual.review_count) : null, rating: manual.rating ? Number(manual.rating) : null }), "Profile audited").then(o.reload); }}>
                  {(["name", "primary_category", "address", "phone", "website"] as const).map((k) => <Field key={k} label={humanize(k)}><Input value={manual[k]} onChange={(e) => setManual({ ...manual, [k]: e.target.value })} /></Field>)}
                  <Field label="Services (comma separated)"><Input value={manual.services} onChange={(e) => setManual({ ...manual, services: e.target.value })} /></Field>
                  <Field label="Review count"><Input type="number" min={0} value={manual.review_count} onChange={(e) => setManual({ ...manual, review_count: e.target.value })} /></Field>
                  <Field label="Rating"><Input type="number" min={1} max={5} step={0.1} value={manual.rating} onChange={(e) => setManual({ ...manual, rating: e.target.value })} /></Field>
                  <Field label="Description" className="sm:col-span-2"><Textarea value={manual.description} onChange={(e) => setManual({ ...manual, description: e.target.value })} /></Field>
                  <div className="sm:col-span-2"><Button type="submit" loading={busy === "manual"}>Audit</Button></div>
                </form>
              </details>
            </div>
          </Card>
          {d.latest_audit && <Card title={`Latest audit · ${d.latest_audit.completeness}% complete`} actions={<span className="flex items-center gap-2 text-xs text-muted"><SourceBadge source={d.latest_audit.source} /> {formatDateTime(d.latest_audit.fetched_at)}</span>}>
            <ul className="divide-y divide-border/60">{d.latest_audit.findings.map((f) => (
              <li key={f.code} className="space-y-1 px-4 py-3 text-sm">
                <p className="font-medium">{f.issue} <span className="text-xs text-muted">· {humanize(f.priority)} priority</span></p>
                <p className="text-xs text-muted">{f.explanation} {f.recommendation}</p>
                {f.suggested_correction && <div className="flex items-start gap-2 rounded-lg bg-surface-2 p-2 text-xs"><span className="flex-1">Suggested: {f.suggested_correction}</span><button aria-label="Copy" onClick={() => { navigator.clipboard?.writeText(f.suggested_correction ?? ""); toast("Copied - update it in Business Profile"); }}><Copy className="h-3.5 w-3.5" /></button></div>}
              </li>))}</ul>
            <p className="px-4 pb-3 text-xs text-muted">Every change needs your approval: copy the suggestion and update your profile on Google.</p>
          </Card>}
        </>}

        {tab === "posts" && <Card title="Draft a Business Profile post">
          <form className="grid gap-3 p-4 sm:grid-cols-[160px_1fr_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); setPicture(null); run("draft", () => post<typeof draft>("/local/posts/draft", post_)).then((r) => r && setDraft(r)); }}>
            <Field label="Type"><Select value={post_.kind} onChange={(e) => setPost({ ...post_, kind: e.target.value })} options={["update", "offer", "event", "service"]} /></Field>
            <Field label="Details (your facts)"><Input value={post_.details} onChange={(e) => setPost({ ...post_, details: e.target.value })} placeholder="e.g. New 6 AM women's batch from 1 Dec" /></Field>
            <Button type="submit" loading={busy === "draft"}><Sparkles className="h-4 w-4" /> Draft</Button>
          </form>
          {draft && <div className="space-y-2 border-t border-border p-4">
            <SourceBadge source={draft.generated_by} />
            <Textarea rows={5} value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
            {draft.warnings.length > 0 && <Note tone="warning">Check before posting: {draft.warnings.join("; ")}</Note>}
            {picture && (
              <div className="flex flex-wrap items-end gap-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={picture} alt="Picture for this post" className="h-48 w-48 rounded-2xl object-cover" />
                <a href={picture} download="gym-post.png" className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm font-semibold hover:bg-surface-2"><Download className="h-4 w-4" /> Download picture</a>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => { navigator.clipboard?.writeText(draft.text); toast("Copied"); }}><Copy className="h-4 w-4" /> Copy</Button>
              <Button variant="secondary" loading={busy === "img"} onClick={() => run("img", () => post<{ image: string }>("/local/posts/image", { text: draft.text })).then((r) => r && setPicture(r.image))}><ImageIcon className="h-4 w-4" /> {picture ? "New picture" : "Create a picture"}</Button>
              {connected && <Button loading={busy === "pub"} onClick={() => run("pub", () => post("/local/posts/publish", { text: draft.text, call_to_action: draft.call_to_action === "CALL" ? "CALL" : undefined }), "Posted to Google").then(() => setDraft(null))}>Approve & publish</Button>}
            </div>
          </div>}
        </Card>}
      </>}
    </FeatureGate>
  );
}
