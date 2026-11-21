"use client";

import { Bot, Check, ChevronDown, Send, Sparkles, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { FeatureGate, MiniMarkdown, SourceBadge, useAction } from "@/components/shared/growth";
import { Button, Card, Input, PageHeader, Spinner } from "@/components/shared/ui";
import { post } from "@/services/api";

interface Reply {
  reply: string | null; status: string; engine: string; conversation_id: string; agent: string; agent_name: string;
  pending_actions: { id: string; summary: string; tool: string }[];
  tools_called: { name: string; ok: boolean; denied?: boolean; pending?: boolean }[];
  evidence: { tool: string; result: unknown }[];
}
type Msg = { role: "user" | "assistant"; text: string; meta?: Reply };

const PROMPTS = ["How is my gym performing this month?", "Which leads should I follow up with today?",
  "How much money is outstanding?", "Which memberships expire this week?", "How much revenue was recovered?",
  "Which lead source brings the most paying members?", "Is my website SEO improving?",
  "What are my top five revenue opportunities?", "Give me a seven-day growth plan"];

function ActionCard({ action }: { action: { id: string; summary: string } }) {
  const { busy, run } = useAction();
  const [state, setState] = useState<"pending" | "done" | "rejected">("pending");
  return (
    <div className="mt-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
      <p className="font-medium text-warning">Needs your confirmation</p>
      <p className="mt-0.5 text-fg">{action.summary}</p>
      {state === "pending" ? (
        <div className="mt-2 flex gap-2">
          <Button size="sm" loading={busy === "c"} onClick={() => run("c", () => post<{ status: string }>(`/ai/actions/${action.id}/confirm`),
            (r) => `Action ${r.status}`).then((r) => r && setState("done"))}><Check className="h-3.5 w-3.5" /> Confirm</Button>
          <Button size="sm" variant="secondary" loading={busy === "r"} onClick={() => run("r", () => post(`/ai/actions/${action.id}/reject`), "Rejected").then((r) => r && setState("rejected"))}><X className="h-3.5 w-3.5" /> Reject</Button>
        </div>
      ) : <p className="mt-1 text-xs text-muted">{state === "done" ? "Confirmed." : "Rejected - nothing was done."}</p>}
    </div>
  );
}

function Evidence({ meta }: { meta: Reply }) {
  const [open, setOpen] = useState(false);
  if (!meta.tools_called.length) return null;
  return (
    <div className="mt-2 text-xs text-muted">
      <button onClick={() => setOpen(!open)} className="inline-flex items-center gap-1 hover:text-fg">
        <ChevronDown className={`h-3 w-3 transition ${open ? "" : "-rotate-90"}`} /> Data used: {meta.tools_called.map((t) => t.name.replace(/_/g, " ")).join(", ")}
      </button>
      {open && <pre className="mt-1 max-h-64 overflow-auto rounded-lg bg-surface-2 p-2 text-[11px]">{JSON.stringify(meta.evidence, null, 2)}</pre>}
    </div>
  );
}

export default function AssistantPage() {
  const params = useSearchParams();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [conv, setConv] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const { run } = useAction();
  const end = useRef<HTMLDivElement>(null);
  const asked = useRef(false);

  async function send(message: string) {
    if (!message.trim() || sending) return;
    setMsgs((m) => [...m, { role: "user", text: message }]);
    setText("");
    setSending(true);
    const r = await run("ask", () => post<Reply>("/ai/assistant", { message, conversation_id: conv }));
    setSending(false);
    if (r) {
      setConv(r.conversation_id);
      setMsgs((m) => [...m, { role: "assistant", text: r.reply ?? "No answer.", meta: r }]);
    }
  }

  useEffect(() => {
    const q = params.get("q");
    if (q && !asked.current) { asked.current = true; send(q); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [msgs, sending]);

  return (
    <FeatureGate feature="business_analyst">
      <PageHeader title="AI growth assistant" description="Ask about leads, trials, renewals, payments, SEO and reviews. Answers use your data through GymFlow's tools; actions that send messages need your confirmation." />
      <Card className="flex h-[calc(100vh-13rem)] min-h-[420px] flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {!msgs.length && (
            <div className="mx-auto max-w-xl py-6 text-center">
              <Sparkles className="mx-auto h-6 w-6 text-brand" />
              <p className="mt-2 font-medium">What would you like to know?</p>
              <div className="mt-4 flex flex-wrap justify-center gap-1.5">
                {PROMPTS.map((p) => <button key={p} onClick={() => send(p)} className="rounded-full border border-border px-3 py-1.5 text-xs text-muted hover:border-brand/50 hover:text-fg">{p}</button>)}
              </div>
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex gap-2"}>
              {m.role === "assistant" && <Bot className="mt-1 h-5 w-5 shrink-0 text-brand" />}
              <div className={m.role === "user" ? "max-w-[80%] rounded-2xl rounded-br-sm bg-brand px-3.5 py-2 text-sm text-brand-fg" : "max-w-[90%] rounded-2xl rounded-tl-sm bg-surface-2 px-3.5 py-2.5"}>
                {m.role === "user" ? m.text : <>
                  <div className="mb-1 flex items-center gap-2 text-[11px] text-muted">{m.meta?.agent_name} <SourceBadge source={m.meta?.engine} /></div>
                  <MiniMarkdown text={m.text} />
                  {m.meta?.pending_actions.map((a) => <ActionCard key={a.id} action={a} />)}
                  {m.meta && <Evidence meta={m.meta} />}
                </>}
              </div>
            </div>
          ))}
          {sending && <div className="flex items-center gap-2 text-sm text-muted"><Spinner className="h-4 w-4" /> Checking your data…</div>}
          <div ref={end} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex gap-2 border-t border-border p-3">
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask a question about your gym…" aria-label="Message" />
          <Button type="submit" disabled={sending || !text.trim()} aria-label="Send"><Send className="h-4 w-4" /></Button>
        </form>
      </Card>
    </FeatureGate>
  );
}
