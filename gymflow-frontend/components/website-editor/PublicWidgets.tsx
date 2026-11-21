"use client";

import { MessageCircle, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const KEY = "gf_attribution";

export interface Attribution { utm_source?: string; utm_medium?: string; utm_campaign?: string; utm_content?: string; referrer?: string; landing_page?: string }

/** Only what the browser actually saw: UTM tags on the first page of the visit and the external referrer. */
export function captureAttribution(landingPage?: string): Attribution {
  if (typeof window === "undefined") return {};
  let stored: Attribution = {};
  try { stored = JSON.parse(sessionStorage.getItem(KEY) ?? "{}"); } catch { /* storage blocked */ }
  const q = new URLSearchParams(window.location.search);
  const fresh: Attribution = {};
  for (const k of ["utm_source", "utm_medium", "utm_campaign", "utm_content"] as const) {
    const v = q.get(k);
    if (v) fresh[k] = v.slice(0, 100);
  }
  const ref = document.referrer && !document.referrer.startsWith(window.location.origin) ? document.referrer.slice(0, 1000) : undefined;
  const merged: Attribution = { ...stored, ...fresh, ...(ref && !stored.referrer ? { referrer: ref } : {}), ...(landingPage ? { landing_page: landingPage } : {}) };
  try { sessionStorage.setItem(KEY, JSON.stringify(merged)); } catch { /* ignore */ }
  return merged;
}

function sessionId(): string {
  try {
    let id = localStorage.getItem("gf_chat_session");
    if (!id) { id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join(""); localStorage.setItem("gf_chat_session", id); }
    return id;
  } catch {
    return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
  }
}

export function TrialBooking({ slug, landingPage }: { slug: string; landingPage?: string }) {
  const [slots, setSlots] = useState<{ starts_at: string; label: string }[] | null>(null);
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    fetch(`${API}/public/sites/${slug}/trial-slots`).then((r) => (r.ok ? r.json() : null)).then((d) => setSlots(d?.enabled ? d.slots : [])).catch(() => setSlots([]));
  }, [slug]);
  if (!slots?.length) return null;
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setState("sending");
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    const res = await fetch(`${API}/public/sites/${slug}/trials`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...captureAttribution(landingPage), name: f.name, phone: f.phone, starts_at: f.starts_at, whatsapp_opt_in: f.whatsapp_opt_in === "on", website: f.website || undefined }) });
    const body = await res.json().catch(() => null);
    if (res.ok) { setState("done"); setMsg(body?.message ?? "Booked!"); } else { setState("error"); setMsg(typeof body?.detail === "string" ? body.detail : "Please check your details"); }
  }
  const input = "w-full rounded-lg border px-3 py-2.5 text-sm outline-none";
  const style = { background: "var(--site-bg)", borderColor: "var(--site-border)", color: "var(--site-fg)" };
  if (state === "done") return <p className="rounded-lg p-4" style={{ background: "var(--site-bg)" }}>{msg}</p>;
  return (
    <form onSubmit={submit} className="mt-6 grid gap-3 rounded-xl border p-4" style={{ borderColor: "var(--site-border)" }}>
      <p className="font-semibold">Book a trial session</p>
      <select name="starts_at" required className={input} style={style}>{slots.map((s) => <option key={s.starts_at} value={s.starts_at}>{s.label}</option>)}</select>
      <input name="name" required placeholder="Your name" className={input} style={style} />
      <input name="phone" required placeholder="Phone number" inputMode="tel" className={input} style={style} />
      <input name="website" tabIndex={-1} autoComplete="off" aria-hidden className="hidden" />
      <label className="flex items-center gap-2 text-xs" style={{ color: "var(--site-muted)" }}><input type="checkbox" name="whatsapp_opt_in" /> Send me the confirmation and reminders on WhatsApp</label>
      {state === "error" && <p className="text-sm text-red-500">{msg}</p>}
      <button disabled={state === "sending"} className="rounded-lg px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60" style={{ background: "var(--site-primary)" }}>{state === "sending" ? "Booking…" : "Book trial"}</button>
    </form>
  );
}

export function ChatWidget({ slug, gymName, landingPage }: { slug: string; gymName: string; landingPage?: string }) {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<{ role: "me" | "gym"; text: string }[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [disabled, setDisabled] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [msgs, open]);
  if (disabled) return null;
  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = text.trim();
    if (!message) return;
    setMsgs((m) => [...m, { role: "me", text: message }]);
    setText("");
    setSending(true);
    try {
      const res = await fetch(`${API}/public/sites/${slug}/chat`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId(), message, ...captureAttribution(landingPage) }) });
      const body = await res.json();
      if (body.status === "disabled") { setDisabled(true); return; }
      setMsgs((m) => [...m, { role: "gym", text: body.reply ?? "Thanks! A team member will reply here shortly." }]);
    } catch {
      setMsgs((m) => [...m, { role: "gym", text: "Sorry, chat isn't available right now. Please use the form or call us." }]);
    } finally {
      setSending(false);
    }
  }
  return (
    <div className="fixed bottom-4 right-4 z-50">
      {open ? (
        <div className="flex h-[28rem] w-[min(92vw,360px)] flex-col overflow-hidden rounded-2xl border shadow-2xl" style={{ background: "var(--site-bg)", borderColor: "var(--site-border)", color: "var(--site-fg)" }}>
          <div className="flex items-center justify-between px-4 py-3 text-white" style={{ background: "var(--site-primary)" }}>
            <p className="text-sm font-semibold">Chat with {gymName}</p>
            <button aria-label="Close chat" onClick={() => setOpen(false)}><X className="h-4 w-4" /></button>
          </div>
          <div className="flex-1 space-y-2 overflow-y-auto p-3 text-sm">
            {!msgs.length && <p style={{ color: "var(--site-muted)" }}>Hi! Ask about plans, timings, or book a free trial. An AI assistant answers from the gym&apos;s information and hands over to staff when needed.</p>}
            {msgs.map((m, i) => <div key={i} className={m.role === "me" ? "flex justify-end" : "flex"}><p className="max-w-[85%] whitespace-pre-line rounded-2xl px-3 py-2" style={m.role === "me" ? { background: "var(--site-primary)", color: "#fff" } : { background: "var(--site-surface)" }}>{m.text}</p></div>)}
            {sending && <p style={{ color: "var(--site-muted)" }}>Typing…</p>}
            <div ref={end} />
          </div>
          <form onSubmit={send} className="flex gap-2 border-t p-2" style={{ borderColor: "var(--site-border)" }}>
            <input value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} placeholder="Type a message" aria-label="Message" className="flex-1 rounded-lg border px-3 py-2 text-sm outline-none" style={{ background: "var(--site-bg)", borderColor: "var(--site-border)", color: "var(--site-fg)" }} />
            <button aria-label="Send" disabled={sending} className="rounded-lg px-3 text-white" style={{ background: "var(--site-primary)" }}><Send className="h-4 w-4" /></button>
          </form>
        </div>
      ) : (
        <button onClick={() => setOpen(true)} aria-label="Open chat" className="flex h-14 w-14 items-center justify-center rounded-full text-white shadow-xl" style={{ background: "var(--site-primary)" }}>
          <MessageCircle className="h-6 w-6" />
        </button>
      )}
    </div>
  );
}

/** Safe JSON-LD script (escapes "<" so content can't close the script tag). */
export function JsonLd({ data }: { data: unknown }) {
  if (!data || (Array.isArray(data) && !data.length)) return null;
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }} />;
}
