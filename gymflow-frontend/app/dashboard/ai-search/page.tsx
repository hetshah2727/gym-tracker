"use client";

import { Check, Copy, Play, Plus, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { FeatureGate, Kpi, MiniMarkdown, Note, SourceBadge, useAction, useEntitlements, useQueryTab, useToast } from "@/components/shared/growth";
import { Button, Card, EmptyState, Field, Input, Loading, PageHeader, Select, Tabs, Textarea } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, humanize } from "@/lib/utils";
import { del, post } from "@/services/api";

interface Check_ { key: string; label: string; weight: number; passed: boolean; evidence: string; fix: string | null }
interface Readiness { latest: { score: number; checklist: Check_[]; inconsistencies: { field: string; profile: string; other_source: string; value: unknown }[]; content_gaps: { label: string; fix: string }[]; created_at: string } | null; history: { score: number; at: string }[]; disclaimer: string }
interface Validation { valid: boolean; errors: string[]; warnings: string[] }
interface Visibility { queries: { id: string; question: string; runs: number; mentioned: number; last: { provider: string; method?: string; mentioned: boolean; position: number | null; observed_at: string } | null }[]; providers: Record<string, { runs: number; mentioned: number; mention_rate: number | null }>; top_competitors: [string, number][]; sample_size: number; limitations: string }
type Tab = "readiness" | "schema" | "content" | "monitoring";

export default function AiSearchPage() {
  const [tab, setTab] = useQueryTab<Tab>("readiness");
  const ready = useApi<Readiness>(tab === "readiness" ? "/ai-search/readiness" : null);
  const { ent } = useEntitlements();
  const canMonitor = ent?.features.ai_search_monitoring !== false;
  const vis = useApi<Visibility>(tab === "monitoring" && canMonitor ? "/ai-search/visibility" : null);
  const types = useApi<Record<string, string>>(tab === "content" ? "/ai-search/content/types" : null);
  const sites = useApi<{ id: string; name: string }[]>(tab === "schema" ? "/websites" : null);
  const [kind, setKind] = useState("local_business");
  const [json, setJson] = useState("");
  const [validation, setValidation] = useState<Validation | null>(null);
  const [studio, setStudio] = useState({ kind: "service_explanation", topic: "" });
  const [draft, setDraft] = useState<{ title: string; body_markdown?: string; faqs?: { q: string; a: string }[]; generated_by: string; warnings: string[] } | null>(null);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<{ query: string; provider: string; mentioned: boolean; position: string; competitors: string }>({ query: "", provider: "chatgpt", mentioned: false, position: "", competitors: "" });
  const { busy, run } = useAction();
  const toast = useToast();
  const r = ready.data?.latest;

  return (
    <FeatureGate feature="ai_search_readiness">
      <PageHeader title="AI search visibility" description="Make your gym's information clear, consistent and structured so AI assistants and search engines describe it correctly. No AI mention is ever guaranteed." />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ value: "readiness", label: "Checklist" }, { value: "content", label: "Write content" }, { value: "monitoring", label: "Where you appear" }, { value: "schema", label: "For your web developer" }]} />

      {tab === "readiness" && <>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Button loading={busy === "run"} onClick={() => run("run", () => post("/ai-search/readiness"), "Checklist updated").then(ready.reload)}><Play className="h-4 w-4" /> Run readiness check</Button>
          <Link href="/dashboard/gym-profile" className="text-sm text-brand">Edit the gym entity profile</Link>
        </div>
        {ready.loading ? <Loading /> : !r ? <EmptyState title="Not checked yet" description="Uses your Gym Profile and the latest website audit." /> : <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Readiness (checklist)" value={`${r.score}/100`} hint={formatDateTime(r.created_at)} />
            <Kpi label="Checks passed" value={`${r.checklist.filter((c) => c.passed).length}/${r.checklist.length}`} />
            <Kpi label="Content gaps" value={r.content_gaps.length} tone={r.content_gaps.length ? "warning" : undefined} />
            <Kpi label="Inconsistencies" value={r.inconsistencies.length} tone={r.inconsistencies.length ? "danger" : undefined} />
          </div>
          <Note className="mt-3">{ready.data?.disclaimer}</Note>
          <Card title="Checklist" className="mt-4">
            <ul className="divide-y divide-border/60">{r.checklist.map((c) => (
              <li key={c.key} className="flex gap-3 px-4 py-3 text-sm">
                {c.passed ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand" aria-label="Passed" /> : <X className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-label="Failed" />}
                <div><p className="font-medium">{c.label} <span className="text-xs text-muted">({c.weight} pts)</span></p><p className="text-xs text-muted">{c.evidence}</p>{c.fix && <p className="text-xs">Fix: {c.fix}</p>}</div>
              </li>))}</ul>
          </Card>
          {r.inconsistencies.length > 0 && <Card title="Business information inconsistencies" className="mt-4"><table className="table-base"><thead><tr><th>Field</th><th>Gym profile</th><th>Other source</th><th>Value there</th></tr></thead>
            <tbody>{r.inconsistencies.map((i, n) => <tr key={n}><td>{i.field}</td><td>{i.profile}</td><td>{i.other_source}</td><td>{String(i.value)}</td></tr>)}</tbody></table></Card>}
        </>}
      </>}

      {tab === "schema" && <Card title="Website code for search engines (JSON-LD)">
        <div className="space-y-3 p-4">
          <div className="flex flex-wrap gap-2">
            <Select className="w-56" value={kind} onChange={(e) => setKind(e.target.value)} options={[{ value: "local_business", label: "Gym (ExerciseGym)" }, { value: "organization", label: "Organization" }, { value: "website", label: "WebSite" }, { value: "services", label: "Services" }, { value: "faq", label: "FAQ page (approved FAQs)" }]} />
            <Button loading={busy === "gen"} onClick={() => run("gen", () => post<{ json_ld: unknown; validation: Validation }>("/ai-search/schema/generate", { kind })).then((x) => { if (x) { setJson(JSON.stringify(x.json_ld, null, 2)); setValidation(x.validation); } })}>Generate from profile</Button>
            <Button variant="secondary" disabled={!json} onClick={() => run("val", () => post<Validation>("/ai-search/schema/validate", { json_ld: json })).then((v) => v && setValidation(v))}>Validate</Button>
          </div>
          <Textarea rows={14} className="font-mono text-xs" value={json} onChange={(e) => { setJson(e.target.value); setValidation(null); }} placeholder="Generate, or paste JSON-LD to validate" />
          {validation && <Note tone={validation.valid ? "success" : "warning"}>{validation.valid ? "Valid." : "Errors: " + validation.errors.join("; ")}{validation.warnings.length > 0 && <span className="block">Warnings: {validation.warnings.join("; ")}</span>}</Note>}
          <p className="text-xs text-muted">Ratings and reviews are never added to structured data.</p>
          {validation?.valid && <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => { navigator.clipboard?.writeText(`<script type="application/ld+json">\n${json}\n</script>`); toast("Copied - paste into your site's <head>"); }}><Copy className="h-4 w-4" /> Copy snippet</Button>
            {sites.data?.map((s) => <Button key={s.id} loading={busy === "pub" + s.id} onClick={() => run("pub" + s.id, () => post("/ai-search/schema/publish", { website_id: s.id, json_ld: [JSON.parse(json)].flat() }), "Approved for your GymFlow site - republish the site to go live")}>Approve for {s.name}</Button>)}
          </div>}
        </div>
      </Card>}

      {tab === "content" && <Card title="Content studio">
        <form className="grid gap-3 p-4 sm:grid-cols-[240px_1fr_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); run("c", () => post<typeof draft>("/ai-search/content", { kind: studio.kind, topic: studio.topic || undefined })).then((d) => d && setDraft(d)); }}>
          <Field label="Content type"><Select value={studio.kind} onChange={(e) => setStudio({ ...studio, kind: e.target.value })} options={Object.keys(types.data ?? { faqs: "", service_explanation: "" }).map((k) => ({ value: k, label: humanize(k) }))} /></Field>
          <Field label="Topic (optional)"><Input value={studio.topic} onChange={(e) => setStudio({ ...studio, topic: e.target.value })} placeholder="e.g. Personal training, Gotri, a trainer's name" /></Field>
          <Button type="submit" loading={busy === "c"}>Draft</Button>
        </form>
        <p className="px-4 text-xs text-muted">Written only from your approved profile, plans and trainers. Review every draft - especially anything about results or health.</p>
        {draft && <div className="space-y-3 border-t border-border p-4 mt-3">
          <div className="flex items-center gap-2"><p className="font-medium">{draft.title}</p><SourceBadge source={draft.generated_by} /></div>
          {draft.warnings.length > 0 && <Note tone="warning">Check these claims: {draft.warnings.join("; ")}</Note>}
          {draft.body_markdown && <div className="rounded-lg bg-surface-2 p-3"><MiniMarkdown text={draft.body_markdown} /></div>}
          {draft.faqs && <ul className="space-y-2">{draft.faqs.map((f) => <li key={f.q} className="rounded-lg bg-surface-2 p-3 text-sm"><p className="font-medium">{f.q}</p><p className="text-muted">{f.a}</p></li>)}</ul>}
          <Button variant="secondary" onClick={() => { navigator.clipboard?.writeText(draft.body_markdown ?? (draft.faqs ?? []).map((f) => `${f.q}\n${f.a}`).join("\n\n")); toast("Copied"); }}><Copy className="h-4 w-4" /> Copy</Button>
        </div>}
      </Card>}

      {tab === "monitoring" && (!canMonitor ? <FeatureGate feature="ai_search_monitoring"><span /></FeatureGate> : vis.loading || !vis.data ? <Loading /> : <>
        <Note className="mb-4">{vis.data.limitations}</Note>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Kpi label="Samples recorded" value={vis.data.sample_size} />
          {Object.entries(vis.data.providers).slice(0, 3).map(([p, v]) => <Kpi key={p} label={`Mentioned on ${humanize(p)}`} value={`${v.mentioned}/${v.runs}`} hint="sampled answers" />)}
        </div>
        <Card title="Questions you monitor" className="mt-4">
          <form className="flex gap-2 border-b border-border p-3" onSubmit={(e) => { e.preventDefault(); run("q", () => post("/ai-search/visibility/queries", { question }), "Question added").then(() => { setQuestion(""); vis.reload(); }); }}>
            <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Best gyms in Gotri, Vadodara" /><Button type="submit" variant="secondary" disabled={question.length < 5}><Plus className="h-4 w-4" /> Add</Button>
          </form>
          {!vis.data.queries.length ? <EmptyState title="No questions yet" /> : <ul className="divide-y divide-border/60">{vis.data.queries.map((q) => (
            <li key={q.id} className="flex items-center justify-between px-4 py-3 text-sm"><div><p className="font-medium">{q.question}</p><p className="text-xs text-muted">{q.runs ? `Mentioned in ${q.mentioned} of ${q.runs} samples · last: ${q.last?.provider} ${q.last?.mentioned ? `(position ${q.last.position ?? "?"})` : "(not mentioned)"}` : "No samples yet"} <SourceBadge source={q.last?.method ?? "manual_research"} /></p></div>
              <div className="flex items-center gap-2">
              <Button size="sm" variant="secondary" loading={busy === `chk-${q.id}`} onClick={() => run(`chk-${q.id}`, () => post<{ mentioned: boolean; position: number | null; sources: unknown[] }>(`/ai-search/visibility/queries/${q.id}/check`),
                (r) => r.mentioned ? `You're mentioned${r.position ? ` at #${r.position}` : ""} (${r.sources.length} sources checked)` : `Not mentioned this time (${r.sources.length} sources checked)`).then(vis.reload)}>Check on Google now</Button>
              <button aria-label="Remove question" onClick={() => run("dq", () => del(`/ai-search/visibility/queries/${q.id}`)).then(vis.reload)} className="text-muted hover:text-danger"><X className="h-4 w-4" /></button></div></li>))}</ul>}
        </Card>
        <Card title="Record a research sample" className="mt-4">
          <form className="grid gap-3 p-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); run("res", () => post(`/ai-search/visibility/queries/${result.query}/results`, { provider: result.provider, mentioned: result.mentioned, position: result.position ? Number(result.position) : null, competitors_mentioned: result.competitors.split(",").map((s) => s.trim()).filter(Boolean) }), "Sample recorded").then(vis.reload); }}>
            <Field label="Question"><Select required value={result.query} onChange={(e) => setResult({ ...result, query: e.target.value })} placeholder="Choose" options={vis.data.queries.map((q) => ({ value: q.id, label: q.question }))} /></Field>
            <Field label="Assistant"><Select value={result.provider} onChange={(e) => setResult({ ...result, provider: e.target.value })} options={["chatgpt", "gemini", "perplexity", "copilot", "google_ai_overview", "claude", "other"]} /></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={result.mentioned} onChange={(e) => setResult({ ...result, mentioned: e.target.checked })} /> Our gym was mentioned</label>
            <Field label="Position (if listed)"><Input type="number" min={1} value={result.position} onChange={(e) => setResult({ ...result, position: e.target.value })} /></Field>
            <Field label="Competitors mentioned (comma separated)" className="sm:col-span-2"><Input value={result.competitors} onChange={(e) => setResult({ ...result, competitors: e.target.value })} /></Field>
            <div className="sm:col-span-2"><Button type="submit" loading={busy === "res"} disabled={!result.query}>Save sample</Button></div>
          </form>
        </Card>
      </>)}
    </FeatureGate>
  );
}
