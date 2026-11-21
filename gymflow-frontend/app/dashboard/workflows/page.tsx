"use client";

import { Play } from "lucide-react";
import { Note, useAction } from "@/components/shared/growth";
import { Button, Card, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, humanize } from "@/lib/utils";
import { post } from "@/services/api";

interface Wf { key: string; name: string; trigger: string; steps: string[]; runs_30d: Record<string, number>; last_event_at: string | null }
interface Data { workflows: Wf[]; daily_job: { last_run_at: string | null; last_result: Record<string, unknown> | null }; recent_events: { type: string; actor: string; entity_type: string | null; at: string }[] }

export default function WorkflowsPage() {
  const { data, loading, reload } = useApi<Data>("/growth/workflows");
  const { busy, run } = useAction();
  return (
    <>
      <PageHeader title="Workflow center" description="The automations that connect enquiries, trials, memberships, payments and visibility. They run inside GymFlow and are safe to re-run."
        actions={<Button loading={busy === "run"} onClick={() => run("run", () => post("/growth/workflows/daily/run"), "Daily workflows ran").then(reload)}><Play className="h-4 w-4" /> Run daily workflows now</Button>} />
      {loading || !data ? <Loading /> : <>
        <Note className="mb-4">Daily job last ran: {data.daily_job.last_run_at ? formatDateTime(data.daily_job.last_run_at) : "never"}{data.daily_job.last_result && ` - ${Object.entries(data.daily_job.last_result).filter(([k]) => k !== "daily_report").map(([k, v]) => `${humanize(k)} ${typeof v === "object" ? Object.values(v as object).reduce((a: number, b) => a + Number(b), 0) : v}`).join(", ")}`}. These run automatically every day.</Note>
        <div className="grid gap-4 md:grid-cols-2">{data.workflows.map((w) => (
          <Card key={w.key} title={w.name}>
            <div className="space-y-2 p-4 text-sm">
              <p className="text-xs text-muted">Trigger: {w.trigger}</p>
              <ol className="flex flex-wrap items-center gap-1 text-xs">{w.steps.map((s, i) => <li key={s} className="flex items-center gap-1"><span className="rounded-md bg-surface-2 px-2 py-0.5">{s}</span>{i < w.steps.length - 1 && <span className="text-muted">→</span>}</li>)}</ol>
              <p className="text-xs text-muted">Last 30 days: {Object.entries(w.runs_30d).map(([e, n]) => `${e} ×${n}`).join(" · ")}{w.last_event_at && ` · last ${formatDateTime(w.last_event_at)}`}</p>
            </div>
          </Card>))}</div>
        <Card title="Recent events" className="mt-4"><table className="table-base"><thead><tr><th>When</th><th>Event</th><th>By</th></tr></thead>
          <tbody>{data.recent_events.map((e, i) => <tr key={i}><td className="text-xs">{formatDateTime(e.at)}</td><td className="text-xs">{e.type}</td><td className="text-xs">{e.actor}</td></tr>)}</tbody></table></Card>
      </>}
    </>
  );
}
