"use client";

import { Check, X } from "lucide-react";
import { Kpi, Note, SourceBadge, useAction } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, humanize } from "@/lib/utils";
import { post, put } from "@/services/api";

interface Agent { key: string; name: string; purpose: string; public: boolean; included_in_plan: boolean; tools: { name: string; description: string; consequential: boolean; roles: string[] }[]; config: { enabled: boolean } }
interface Usage { by_agent: Record<string, { runs: number; errors: number; input_tokens: number; output_tokens: number; cost_usd: number; tool_calls: number; denied_tool_calls: number }>; total_cost_usd: number; engine: string; monthly_usage: Record<string, { used: number; limit: number | null }>; recent_runs: { agent: string; engine: string; status: string; ms: number; tools: string[]; at: string; error: string | null }[] }
interface Action { id: string; agent: string; summary: string; created_at: string }

export default function AiSettingsPage() {
  const agents = useApi<{ engine: string; engine_note: string | null; agents: Agent[] }>("/ai/agents");
  const usage = useApi<Usage>("/ai/usage", { days: 30 });
  const actions = useApi<Action[]>("/ai/actions");
  const { run } = useAction();

  return (
    <>
      <PageHeader title="AI settings" description="GymFlow's eight specialised agents share one tool registry. Each tool checks your role and plan; actions that send messages or publish need confirmation." />
      {agents.data?.engine_note && <Note className="mb-4">{agents.data.engine_note}</Note>}
      {usage.data && <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Object.entries(usage.data.monthly_usage).map(([k, v]) => <Kpi key={k} label={`${humanize(k)} this month`} value={`${v.used}${v.limit != null ? ` / ${v.limit}` : ""}`} />)}
        <Kpi label="AI cost (30 days)" value={`$${usage.data.total_cost_usd.toFixed(2)}`} hint={usage.data.engine === "rules" ? "Quick answers from your data – no AI cost" : "Estimated"} />
      </div>}
      {!!actions.data?.length && <Card title="Waiting for your confirmation" className="mt-4"><ul className="divide-y divide-border/60">{actions.data.map((a) => (
        <li key={a.id} className="flex items-center justify-between gap-2 px-4 py-3 text-sm"><span>{a.summary} <span className="text-xs text-muted">· {humanize(a.agent)} · {formatDateTime(a.created_at)}</span></span>
          <span className="flex gap-2"><Button size="sm" onClick={() => run("c" + a.id, () => post(`/ai/actions/${a.id}/confirm`), "Done").then(actions.reload)}><Check className="h-3.5 w-3.5" /></Button><Button size="sm" variant="secondary" onClick={() => run("r" + a.id, () => post(`/ai/actions/${a.id}/reject`), "Rejected").then(actions.reload)}><X className="h-3.5 w-3.5" /></Button></span></li>))}</ul></Card>}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {agents.loading ? <Loading /> : agents.data?.agents.map((a) => {
          const u = usage.data?.by_agent[a.key];
          return (
            <Card key={a.key} title={a.name} actions={<div className="flex items-center gap-2">{!a.included_in_plan && <Badge value="draft" className="!normal-case" />}
              <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={a.config.enabled} onChange={(e) => run(a.key, () => put(`/ai/agents/${a.key}`, { enabled: e.target.checked }), "Saved").then(agents.reload)} /> Enabled</label></div>}>
              <div className="space-y-2 p-4 text-sm">
                <p className="text-muted">{a.purpose}{a.public && " Talks to the public (website chat, WhatsApp)."}{!a.included_in_plan && " Not included in your plan."}</p>
                <ul className="flex flex-wrap gap-1.5">{a.tools.map((t) => <li key={t.name} title={t.description} className={`rounded-full border px-2 py-0.5 text-[11px] ${t.consequential ? "border-warning/40 text-warning" : "border-border text-muted"}`}>{t.name.replace(/_/g, " ")}{t.consequential && " · needs approval"}</li>)}</ul>
                {u && <p className="text-xs text-muted">30 days: {u.runs} runs · {u.tool_calls} tool calls{u.denied_tool_calls ? ` · ${u.denied_tool_calls} denied` : ""}{u.errors ? ` · ${u.errors} errors` : ""} · {u.input_tokens + u.output_tokens} tokens</p>}
              </div>
            </Card>
          );
        })}
      </div>
      <Card title="Recent agent runs (execution log)" className="mt-4">
        {!usage.data?.recent_runs.length ? <EmptyState title="No runs yet" /> : <div className="overflow-x-auto"><table className="table-base">
          <thead><tr><th>When</th><th>Agent</th><th>Engine</th><th>Tools</th><th>Time</th><th>Status</th></tr></thead>
          <tbody>{usage.data.recent_runs.map((r, i) => <tr key={i}><td className="text-xs">{formatDateTime(r.at)}</td><td className="text-xs">{humanize(r.agent)}</td><td><SourceBadge source={r.engine} /></td><td className="text-xs">{r.tools.join(", ") || "—"}</td><td className="text-xs">{r.ms} ms</td><td><Badge value={r.status === "ok" ? "sent" : "failed"} />{r.error && <span className="block text-xs text-danger">{r.error}</span>}</td></tr>)}</tbody>
        </table></div>}
      </Card>
    </>
  );
}
