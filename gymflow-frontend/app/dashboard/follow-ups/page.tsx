"use client";

import { Check, Copy } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { LeadDrawer } from "@/components/growth/LeadDrawer";
import { Pager, useAction, useToast } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, Loading, Modal, PageHeader, Select, Tabs } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, humanize } from "@/lib/utils";
import { post } from "@/services/api";
import type { Page } from "@/types";

interface Task { id: string; title: string; description: string | null; kind: string; status: string; priority: string; due_at: string | null; lead_id: string | null; member_id: string | null; opportunity_id: string | null; source: string; draft_message: string | null; outcome: string | null }
type Due = "overdue" | "today" | "upcoming" | "all";

export default function FollowUpsPage() {
  const params = useSearchParams();
  const [due, setDue] = useState<Due>((params.get("due") as Due) || "all");
  const [kind, setKind] = useState("");
  const [mine, setMine] = useState(false);
  const [offset, setOffset] = useState(0);
  const [lead, setLead] = useState<string | null>(null);
  const [closing, setClosing] = useState<Task | null>(null);
  const [outcome, setOutcome] = useState("");
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ title: "", due_at: "", priority: "medium" });
  const toast = useToast();
  const { busy, run } = useAction();
  const tasks = useApi<Page<Task>>("/crm/tasks", { due: due === "all" ? "" : due, kind, mine, offset, limit: 50 });
  const now = Date.now();

  return (
    <>
      <PageHeader title="Follow-ups" description="Tasks from workflows, the AI agents and your team. Drafted messages are ready to copy." actions={<Button onClick={() => setAdding(true)}>New task</Button>} />
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <Tabs<Due> value={due} onChange={(v) => { setDue(v); setOffset(0); }} tabs={[{ value: "all", label: "All open" }, { value: "overdue", label: "Overdue" }, { value: "today", label: "Due today" }, { value: "upcoming", label: "Upcoming" }]} />
        <div className="flex gap-2">
          <Select className="w-40" value={kind} onChange={(e) => setKind(e.target.value)} placeholder="All types" options={["follow_up", "renewal", "payment", "no_show", "escalation", "review", "seo", "other"]} />
          <label className="flex items-center gap-1.5 whitespace-nowrap text-sm text-muted"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Mine</label>
        </div>
      </div>
      <Card>
        {tasks.error && <div className="p-4"><ErrorNote message={tasks.error} /></div>}
        {tasks.loading ? <Loading /> : !tasks.data?.items.length ? <EmptyState title="Nothing to follow up" description="New enquiries, renewals and no-shows create tasks automatically." /> : (
          <ul className="divide-y divide-border/60">
            {tasks.data.items.map((t) => {
              const overdue = t.due_at && new Date(t.due_at).getTime() < now;
              return (
                <li key={t.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{t.lead_id ? <button className="hover:text-brand" onClick={() => setLead(t.lead_id)}>{t.title}</button> : t.title}</p>
                    <p className="text-xs text-muted">{humanize(t.kind)} · {t.source} · <span className={overdue ? "text-danger" : ""}>{t.due_at ? `due ${formatDateTime(t.due_at)}` : "no due date"}</span></p>
                    {t.description && <p className="mt-0.5 text-xs text-muted">{t.description}</p>}
                    {t.draft_message && <p className="mt-1 rounded-lg bg-surface-2 px-2.5 py-1.5 text-xs">{t.draft_message}</p>}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge value={t.priority === "high" ? "overdue" : t.priority === "medium" ? "pending" : "draft"} />
                    {t.draft_message && <Button size="sm" variant="ghost" onClick={() => { navigator.clipboard?.writeText(t.draft_message ?? ""); toast("Message copied"); }}><Copy className="h-3.5 w-3.5" /> Copy</Button>}
                    <Button size="sm" variant="secondary" onClick={() => setClosing(t)}><Check className="h-3.5 w-3.5" /> Done</Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {tasks.data && <Pager total={tasks.data.total} offset={offset} limit={50} onChange={setOffset} />}
      </Card>
      <Modal open={!!closing} onClose={() => setClosing(null)} title="Complete task">
        <Field label="Outcome (optional)"><Input value={outcome} onChange={(e) => setOutcome(e.target.value)} placeholder="e.g. Called - will visit Saturday" /></Field>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => closing && run("cancel", () => post(`/crm/tasks/${closing.id}/complete`, { outcome: outcome || "Not needed", cancelled: true }), "Task cancelled").then(() => { setClosing(null); setOutcome(""); tasks.reload(); })}>Not needed</Button>
          <Button loading={busy === "done"} onClick={() => closing && run("done", () => post(`/crm/tasks/${closing.id}/complete`, { outcome: outcome || undefined }), "Task completed").then(() => { setClosing(null); setOutcome(""); tasks.reload(); })}>Mark done</Button>
        </div>
      </Modal>
      <Modal open={adding} onClose={() => setAdding(false)} title="New task">
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); run("add", () => post("/crm/tasks", { title: form.title, priority: form.priority, due_at: form.due_at ? new Date(form.due_at).toISOString() : undefined }), "Task created").then((r) => { if (r) { setAdding(false); tasks.reload(); } }); }}>
          <Field label="Title"><Input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Due"><Input type="datetime-local" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} /></Field>
            <Field label="Priority"><Select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} options={["low", "medium", "high"]} /></Field>
          </div>
          <div className="flex justify-end"><Button type="submit" loading={busy === "add"}>Create</Button></div>
        </form>
      </Modal>
      <LeadDrawer leadId={lead} onClose={() => setLead(null)} onChanged={tasks.reload} />
    </>
  );
}
