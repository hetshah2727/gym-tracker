"use client";

import { MessageCircle, Phone, Play, Plus, Send, Workflow } from "lucide-react";
import { useState, type FormEvent } from "react";
import { RuleForm, TRIGGERS } from "@/components/automation/RuleForm";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Loading, Modal, PageHeader, Select, Tabs, Textarea } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { useMemberNames } from "@/hooks/useLookups";
import { formatDateTime } from "@/lib/utils";
import { patch, post } from "@/services/api";
import type { AutomationRule, Notification, Page } from "@/types";

type View = "rules" | "log";

export default function AutomationPage() {
  const [view, setView] = useState<View>("rules");
  const rules = useApi<AutomationRule[]>("/automation/rules");
  const log = useApi<Page<Notification>>(view === "log" ? "/notifications" : null, { limit: 100 });
  const { names } = useMemberNames();
  const [editing, setEditing] = useState<AutomationRule | "new" | null>(null);
  const [broadcast, setBroadcast] = useState(false);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<string | null>(null);

  async function runNow() {
    setRunning(true);
    try {
      const result = await post<Record<string, number>>("/automation/run");
      const total = Object.values(result).reduce((a, b) => a + b, 0);
      setRunResult(total ? `Sent ${total} message${total === 1 ? "" : "s"}.` : "All caught up — nothing to send right now.");
      log.reload();
    } finally {
      setRunning(false);
    }
  }

  async function toggle(rule: AutomationRule) {
    await patch(`/automation/rules/${rule.id}`, { is_active: !rule.is_active });
    rules.reload();
  }

  return (
    <>
      <PageHeader
        title="Automation"
        description="Reminders and messages that go out automatically over WhatsApp and AI voice calls."
        actions={
          <>
            <Button variant="secondary" onClick={() => setBroadcast(true)}><Send className="h-4 w-4" /> Broadcast</Button>
            <Button variant="secondary" onClick={runNow} loading={running}><Play className="h-4 w-4" /> Run now</Button>
            <Button onClick={() => setEditing("new")}><Plus className="h-4 w-4" /> New rule</Button>
          </>
        }
      />
      {runResult && <p className="mb-4 rounded-lg border border-brand/30 bg-brand/10 px-3 py-2 text-sm text-brand">{runResult}</p>}
      <Tabs<View> value={view} onChange={setView} tabs={[{ value: "rules", label: "Rules" }, { value: "log", label: "Message log" }]} />

      {view === "rules" ? (
        rules.loading && !rules.data ? (
          <Loading />
        ) : !rules.data?.length ? (
          <Card><EmptyState icon={<Workflow className="h-8 w-8" />} title="No rules" action={<Button onClick={() => setEditing("new")}>Create a rule</Button>} /></Card>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {rules.data.map((r) => (
              <div key={r.id} className={`card p-4 ${r.is_active ? "" : "opacity-60"}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium">{r.name}</p>
                    <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
                      {r.channel === "voice" ? <Phone className="h-3 w-3" /> : <MessageCircle className="h-3 w-3" />}
                      {TRIGGERS.find((t) => t.value === r.trigger)?.label}
                      {r.offset_days > 0 && ` · ${r.offset_days} day${r.offset_days > 1 ? "s" : ""}`}
                    </p>
                  </div>
                  <label className="relative inline-flex cursor-pointer items-center" title={r.is_active ? "Turn off" : "Turn on"}>
                    <input type="checkbox" className="peer sr-only" checked={r.is_active} onChange={() => toggle(r)} />
                    <span className="h-5 w-9 rounded-full bg-border transition peer-checked:bg-brand" />
                    <span className="absolute left-0.5 h-4 w-4 rounded-full bg-white transition peer-checked:translate-x-4" />
                  </label>
                </div>
                <p className="mt-3 rounded-lg bg-surface-2 p-3 text-sm text-muted">{r.template}</p>
                <div className="mt-3 flex justify-end">
                  <Button size="sm" variant="ghost" onClick={() => setEditing(r)}>Edit</Button>
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        <Card>
          {log.error && <div className="p-4"><ErrorNote message={log.error} /></div>}
          {log.loading && !log.data ? (
            <Loading />
          ) : !log.data?.items.length ? (
            <EmptyState title="No messages yet" description="Messages appear here once rules run or you send a broadcast." />
          ) : (
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead><tr><th>Member</th><th>Channel</th><th>Message</th><th>Status</th><th>When</th></tr></thead>
                <tbody>
                  {log.data.items.map((n) => (
                    <tr key={n.id}>
                      <td className="font-medium">{n.member_id ? names[n.member_id] ?? n.recipient : n.recipient}</td>
                      <td className="capitalize text-muted">{n.channel}</td>
                      <td className="max-w-md truncate text-muted" title={n.message}>{n.message}</td>
                      <td><Badge value={n.status} />{n.error && <p className="mt-1 text-xs text-danger">{n.error}</p>}</td>
                      <td className="whitespace-nowrap text-muted">{formatDateTime(n.sent_at ?? n.scheduled_for)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "New automation rule" : "Edit rule"}>
        {editing !== null && <RuleForm rule={editing === "new" ? undefined : editing} onSaved={() => { setEditing(null); rules.reload(); }} />}
      </Modal>
      <Modal open={broadcast} onClose={() => setBroadcast(false)} title="Broadcast to all active members">
        {broadcast && <BroadcastForm onSent={(msg) => { setBroadcast(false); setRunResult(msg); log.reload(); }} />}
      </Modal>
    </>
  );
}

function BroadcastForm({ onSent }: { onSent: (msg: string) => void }) {
  const [message, setMessage] = useState("Hi {name}, ");
  const [channel, setChannel] = useState("whatsapp");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!confirm("Send this message to every active member?")) return;
    setSending(true);
    try {
      const res = await post<{ queued: number; sent: number }>("/notifications/send", { message, channel, all_active_members: true });
      onSent(`Broadcast sent to ${res.sent} of ${res.queued} members.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send");
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <ErrorNote message={error} />
      <Field label="Channel"><Select value={channel} onChange={(e) => setChannel(e.target.value)} options={[{ value: "whatsapp", label: "WhatsApp" }, { value: "sms", label: "SMS" }]} /></Field>
      <Field label="Message" hint="{name} is replaced with each member's first name."><Textarea rows={5} required value={message} onChange={(e) => setMessage(e.target.value)} /></Field>
      <div className="flex justify-end"><Button type="submit" loading={sending}><Send className="h-4 w-4" /> Send</Button></div>
    </form>
  );
}
