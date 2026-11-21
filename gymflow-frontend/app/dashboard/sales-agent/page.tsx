"use client";

import { Bot, RotateCcw, Send, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { FeatureGate, Note, SourceBadge, useAction, useQueryTab } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, Field, Input, Loading, PageHeader, Tabs } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, humanize } from "@/lib/utils";
import { post, put } from "@/services/api";

interface AgentInfo { key: string; name: string; config: { enabled: boolean; channels: string[]; working_hours: { start?: string; end?: string }; escalation_rules: { keywords?: string[] }; daily_message_limit: number; settings: { after_hours_message?: string } } }
interface Conv { id: string; channel: string; status: string; lead: { id: string; name: string } | null; escalation_reason: string | null; last_message_at: string | null }
interface ConvDetail { id: string; status: string; channel: string; messages: { role: string; content: string; at: string }[] }
type Tab = "test" | "inbox" | "settings";

export default function SalesAgentPage() {
  const [tab, setTab] = useQueryTab<Tab>("test");
  const agents = useApi<{ engine: string; engine_note: string | null; agents: AgentInfo[] }>("/ai/agents");
  const agent = agents.data?.agents.find((a) => a.key === "lead_conversion");
  const convs = useApi<Conv[]>(tab === "inbox" ? "/ai/conversations" : null);
  const [openConv, setOpenConv] = useState<string | null>(null);
  const conv = useApi<ConvDetail>(openConv ? `/ai/conversations/${openConv}` : null);
  const [chat, setChat] = useState<{ role: string; text: string }[]>([]);
  const [chatId, setChatId] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [reply, setReply] = useState("");
  const [cfg, setCfg] = useState<AgentInfo["config"] | null>(null);
  const { busy, run } = useAction();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { if (agent) setCfg(agent.config); }, [agent]);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [chat]);

  async function send() {
    if (!text.trim()) return;
    const msg = text;
    setChat((c) => [...c, { role: "user", text: msg }]);
    setText("");
    const r = await run("send", () => post<{ reply: string | null; status: string; conversation_id: string }>("/ai/sales-agent/test", { message: msg, conversation_id: chatId }));
    if (r) {
      setChatId(r.conversation_id);
      setChat((c) => [...c, { role: "assistant", text: r.reply ?? (r.status === "human" ? "(A staff member has taken over - the AI stays silent.)" : `(No reply: ${r.status})`) }]);
    }
  }

  return (
    <FeatureGate feature="ai_sales_agent">
      <PageHeader title="AI sales agent" description="Answers website chat and WhatsApp enquiries from your approved gym profile, qualifies leads, books trials and hands over to staff."
        actions={agent && <Badge value={agent.config.enabled ? "active" : "cancelled"} />} />
      {agents.data?.engine_note && <Note className="mb-4">{agents.data.engine_note}</Note>}
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ value: "test", label: "Test the agent" }, { value: "inbox", label: "Conversations" }, { value: "settings", label: "Settings" }]} />

      {tab === "test" && <Card className="flex h-[60vh] min-h-[380px] flex-col" title="Chat as a prospect" actions={<Button size="sm" variant="ghost" onClick={() => run("reset", () => post("/ai/sales-agent/test/reset")).then(() => { setChat([]); setChatId(null); })}><RotateCcw className="h-3.5 w-3.5" /> New chat</Button>}>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {!chat.length && <EmptyState icon={<Bot className="h-6 w-6" />} title="Say hi like a customer would" description='Try "What are your fees?", "Do you have parking?" or "I want a free trial, I am Riya, 98xxxxxxxx". Leads and bookings made here are real records.' />}
          {chat.map((m, i) => <div key={i} className={m.role === "user" ? "flex justify-end" : "flex"}><p className={`max-w-[80%] whitespace-pre-line rounded-2xl px-3.5 py-2 text-sm ${m.role === "user" ? "bg-brand text-brand-fg" : "bg-surface-2"}`}>{m.text}</p></div>)}
          <div ref={end} />
        </div>
        <form className="flex gap-2 border-t border-border p-3" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a message…" aria-label="Message" /><Button type="submit" loading={busy === "send"} aria-label="Send"><Send className="h-4 w-4" /></Button>
        </form>
      </Card>}

      {tab === "inbox" && <div className="grid gap-4 lg:grid-cols-5">
        <Card title="Conversations" className="lg:col-span-2">
          {convs.loading ? <Loading /> : !convs.data?.length ? <EmptyState title="No conversations yet" /> : <ul className="divide-y divide-border/60">{convs.data.map((c) => (
            <li key={c.id}><button onClick={() => setOpenConv(c.id)} className={`w-full px-4 py-3 text-left text-sm hover:bg-surface-2 ${openConv === c.id ? "bg-surface-2" : ""}`}>
              <p className="font-medium">{c.lead?.name ?? "Visitor"} <span className="text-xs text-muted">· {humanize(c.channel)}</span></p>
              <p className="text-xs text-muted">{c.status === "human" ? <span className="text-warning">Staff handling{c.escalation_reason ? `: ${c.escalation_reason}` : ""}</span> : humanize(c.status)} · {formatDateTime(c.last_message_at)}</p>
            </button></li>))}</ul>}
        </Card>
        <Card title="Conversation" className="lg:col-span-3">
          {!openConv ? <EmptyState title="Pick a conversation" /> : conv.loading || !conv.data ? <Loading /> : <>
            <div className="flex gap-2 border-b border-border p-3">
              {conv.data.status === "human" ? <Button size="sm" variant="secondary" onClick={() => run("hb", () => post(`/ai/conversations/${openConv}/handback`), "AI resumed").then(() => { conv.reload(); convs.reload(); })}><Bot className="h-3.5 w-3.5" /> Hand back to AI</Button>
                : <Button size="sm" variant="secondary" onClick={() => run("to", () => post(`/ai/conversations/${openConv}/takeover`), "You've taken over - the AI is paused").then(() => { conv.reload(); convs.reload(); })}><UserRound className="h-3.5 w-3.5" /> Take over</Button>}
            </div>
            <div className="max-h-[50vh] space-y-2 overflow-y-auto p-4">{conv.data.messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "flex" : "flex justify-end"}><div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${m.role === "user" ? "bg-surface-2" : m.role === "staff" ? "bg-sky-500/20" : "bg-brand/15"}`}>
                <p className="mb-0.5 text-[10px] uppercase text-muted">{m.role === "assistant" ? "AI" : m.role} · {formatDateTime(m.at)}</p><p className="whitespace-pre-line">{m.content}</p></div></div>))}</div>
            <form className="flex gap-2 border-t border-border p-3" onSubmit={(e) => { e.preventDefault(); run("rep", () => post<{ delivery: { status: string; reason?: string } }>(`/ai/conversations/${openConv}/reply`, { message: reply }), (r) => `Reply ${r.delivery.status}${r.delivery.reason ? `: ${r.delivery.reason}` : ""}`).then(() => { setReply(""); conv.reload(); }); }}>
              <Input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Reply as staff (takes over the chat)" /><Button type="submit" disabled={!reply.trim()}>Send</Button>
            </form>
          </>}
        </Card>
      </div>}

      {tab === "settings" && cfg && <Card title="Lead conversion agent settings">
        <form className="grid gap-4 p-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); run("cfg", () => put("/ai/agents/lead_conversion", cfg), "Settings saved").then(agents.reload); }}>
          <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={cfg.enabled} onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} /> Agent enabled</label>
          <fieldset className="sm:col-span-2"><legend className="label">Channels</legend><div className="flex gap-4 text-sm">{["website_chat", "whatsapp"].map((c) => (
            <label key={c} className="flex items-center gap-2"><input type="checkbox" checked={cfg.channels.includes(c)} onChange={(e) => setCfg({ ...cfg, channels: e.target.checked ? [...cfg.channels, c] : cfg.channels.filter((x) => x !== c) })} /> {humanize(c)}</label>))}</div></fieldset>
          <Field label="Working hours start" hint="Leave both empty to answer 24/7"><Input type="time" value={cfg.working_hours.start ?? ""} onChange={(e) => setCfg({ ...cfg, working_hours: { ...cfg.working_hours, start: e.target.value } })} /></Field>
          <Field label="Working hours end"><Input type="time" value={cfg.working_hours.end ?? ""} onChange={(e) => setCfg({ ...cfg, working_hours: { ...cfg.working_hours, end: e.target.value } })} /></Field>
          <Field label="After-hours reply" className="sm:col-span-2"><Input value={cfg.settings.after_hours_message ?? ""} onChange={(e) => setCfg({ ...cfg, settings: { ...cfg.settings, after_hours_message: e.target.value } })} placeholder="Thanks! Our team is offline and will reply in the morning." /></Field>
          <Field label="Daily AI reply limit"><Input type="number" min={0} value={cfg.daily_message_limit} onChange={(e) => setCfg({ ...cfg, daily_message_limit: Number(e.target.value) })} /></Field>
          <div className="text-xs text-muted sm:col-span-2">Always escalated to staff: complaints, refunds, injuries, medical questions, pregnancy, requests for a person, and anything not in your approved profile. The agent never quotes prices, offers or facilities that aren&apos;t in GymFlow.</div>
          <div className="sm:col-span-2"><Button type="submit" loading={busy === "cfg"}>Save settings</Button></div>
        </form>
        <div className="border-t border-border px-4 py-3 text-xs text-muted">Engine: <SourceBadge source={agents.data?.engine} /></div>
      </Card>}
    </FeatureGate>
  );
}
