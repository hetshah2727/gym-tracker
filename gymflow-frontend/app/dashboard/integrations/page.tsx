"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ConfirmDialog, Note, useAction, useQueryTab, useToast } from "@/components/shared/growth";
import { Badge, Button, Card, Field, Input, Loading, PageHeader, Select, Tabs } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { useRole } from "@/hooks/useRole";
import { formatDateTime, humanize } from "@/lib/utils";
import { del, post, put } from "@/services/api";

interface Item { key: string; name: string; state: string; connection?: string; account?: string | null; last_sync_at?: string | null; last_error?: string | null; detail?: string | null; action?: string; inbound_webhook?: string; webhook_ready?: boolean; templates?: Record<string, string> }
interface GoogleStatus { provider: string; configured: boolean; status: string; account?: string | null; choices: { id: string; label: string; address?: string }[]; last_error?: string | null }
type Tab = "health" | "google" | "whatsapp";
const STATE_TONE: Record<string, string> = { live_tested: "paid", configured_not_tested: "approved", simulation: "pending", not_configured: "draft", not_implemented: "cancelled" };
const CATEGORIES = ["trial_confirmation", "trial_reminder", "sales_follow_up", "renewal_reminder", "payment_reminder", "lead_acknowledgement"];

function GoogleCard({ provider, label, owner }: { provider: string; label: string; owner: boolean }) {
  const st = useApi<GoogleStatus>(`/integrations/google/${provider}/status`);
  const [choice, setChoice] = useState("");
  const [confirm, setConfirm] = useState(false);
  const { busy, run } = useAction();
  const s = st.data;
  return (
    <Card title={label} actions={s && <Badge value={s.status === "connected" ? "active" : s.status === "pending" ? "pending" : s.status === "expired" ? "expired" : "draft"} />}>
      {!s ? <Loading /> : <div className="space-y-3 p-4 text-sm">
        {!s.configured && <Note tone="warning">Google OAuth credentials are not configured on this server, so this can&apos;t be connected yet (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).</Note>}
        {s.status === "connected" && <p>Connected to <strong>{s.account}</strong></p>}
        {s.last_error && <p className="text-xs text-danger">{s.last_error}</p>}
        {s.status === "pending" && <div className="flex gap-2"><Select value={choice} onChange={(e) => setChoice(e.target.value)} placeholder="Choose property / location" options={s.choices.map((c) => ({ value: c.id, label: `${c.label}${c.address ? ` – ${c.address}` : ""}` }))} />
          <Button disabled={!choice} loading={busy === "sel"} onClick={() => run("sel", () => post(`/integrations/google/${provider}/select`, { external_id: choice }), "Connected").then(st.reload)}>Use this</Button></div>}
        {owner && <div className="flex gap-2">
          {s.configured && s.status !== "connected" && <Button loading={busy === "con"} onClick={() => run("con", () => post<{ url: string }>(`/integrations/google/${provider}/connect`)).then((r) => { if (r) window.location.href = r.url; })}>{s.status === "expired" ? "Reconnect" : "Connect Google"}</Button>}
          {s.status !== "not_connected" && <Button variant="secondary" onClick={() => setConfirm(true)}>Disconnect</Button>}
        </div>}
        {!owner && <p className="text-xs text-muted">Only the gym owner can connect accounts.</p>}
      </div>}
      <ConfirmDialog open={confirm} danger title={`Disconnect ${label}?`} message="GymFlow revokes its access token. Synced data stays." confirmLabel="Disconnect" onClose={() => setConfirm(false)}
        onConfirm={() => run("dis", () => del(`/integrations/google/${provider}`), "Disconnected").then(() => { setConfirm(false); st.reload(); })} />
    </Card>
  );
}

export default function IntegrationsPage() {
  const params = useSearchParams();
  const toast = useToast();
  const role = useRole();
  const owner = role === "gym_owner";
  const [tab, setTab] = useQueryTab<Tab>("health");
  const health = useApi<{ integrations: Item[]; legend: Record<string, string> }>("/integrations/health");
  const wa = health.data?.integrations.find((i) => i.key === "whatsapp");
  const [phoneId, setPhoneId] = useState("");
  const [display, setDisplay] = useState("");
  const [templates, setTemplates] = useState<Record<string, string>>({});
  const { busy, run } = useAction();
  useEffect(() => {
    if (params.get("connected")) toast(`${humanize(params.get("connected"))} authorised - now choose the property/location`);
    if (params.get("google_error")) toast(`Google connection cancelled: ${params.get("google_error")}`, "error");
  }, [params, toast]);
  useEffect(() => { if (wa?.templates) setTemplates(wa.templates); }, [wa?.templates]);

  return (
    <>
      <PageHeader title="Integrations" description="Each integration shows exactly what state it is in. Nothing is reported as live unless it has really connected." />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ value: "health", label: "Integration health" }, { value: "google", label: "Google" }, { value: "whatsapp", label: "WhatsApp" }]} />
      {tab === "health" && (health.loading || !health.data ? <Loading /> : <Card>
        <ul className="divide-y divide-border/60">{health.data.integrations.map((i) => (
          <li key={i.key} className="flex flex-col gap-1 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
            <div><p className="font-medium">{i.name}</p><p className="text-xs text-muted">{i.detail ?? (i.account ? `Account: ${i.account}` : "")}{i.last_sync_at && ` · last sync ${formatDateTime(i.last_sync_at)}`}</p>{i.last_error && <p className="text-xs text-danger">{i.last_error}</p>}</div>
            <span title={health.data?.legend[i.state]}><Badge value={STATE_TONE[i.state]} className="!normal-case" /> <span className="text-xs text-muted">{humanize(i.state)}</span></span>
          </li>))}</ul>
        <div className="border-t border-border px-4 py-3 text-xs text-muted">{Object.entries(health.data.legend).map(([k, v]) => <span key={k} className="mr-4 inline-block"><strong>{humanize(k)}:</strong> {v}</span>)}</div>
      </Card>)}
      {tab === "google" && <div className="grid gap-4 lg:grid-cols-2">
        <GoogleCard provider="google_business_profile" label="Google Business Profile" owner={owner} />
        <GoogleCard provider="google_search_console" label="Google Search Console" owner={owner} />
      </div>}
      {tab === "whatsapp" && wa && <div className="grid gap-4 lg:grid-cols-2">
        <Card title="WhatsApp Cloud API">
          <div className="space-y-3 p-4 text-sm">
            <p><Badge value={STATE_TONE[wa.state]} className="!normal-case" /> {humanize(wa.state)} - {wa.detail}</p>
            <p className="text-xs text-muted">Webhook URL for Meta: <code>{wa.inbound_webhook}</code> {wa.webhook_ready ? "(verify token & app secret set)" : "(server needs WHATSAPP_VERIFY_TOKEN and WHATSAPP_APP_SECRET)"}</p>
            <form className="grid gap-2 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); run("wa", () => put("/integrations/whatsapp", { phone_number_id: phoneId, display_number: display || undefined }), "WhatsApp number linked").then(health.reload); }}>
              <Field label="Phone number ID (from Meta)"><Input value={phoneId} onChange={(e) => setPhoneId(e.target.value)} placeholder={wa.connection === "connected" ? "linked - enter to change" : "1234567890"} inputMode="numeric" /></Field>
              <Field label="Display number"><Input value={display} onChange={(e) => setDisplay(e.target.value)} placeholder="+91 98240 12345" /></Field>
              <div className="sm:col-span-2"><Button type="submit" disabled={!owner || !/^\d{5,}$/.test(phoneId)} loading={busy === "wa"}>Link number</Button></div>
            </form>
          </div>
        </Card>
        <Card title="Approved message templates">
          <form className="space-y-2 p-4" onSubmit={(e) => { e.preventDefault(); run("tpl", () => put("/integrations/whatsapp/templates", { templates: Object.fromEntries(Object.entries(templates).filter(([, v]) => v)) }), "Templates saved").then(health.reload); }}>
            <p className="text-xs text-muted">Messages to people who haven&apos;t written in the last 24 hours need a Meta-approved template and their opt-in. Without a template, GymFlow creates a task with the drafted text for staff instead of sending.</p>
            {CATEGORIES.map((c) => <Field key={c} label={humanize(c)}><Input value={templates[c] ?? ""} onChange={(e) => setTemplates({ ...templates, [c]: e.target.value })} placeholder="approved template name" /></Field>)}
            <Button type="submit" disabled={!owner} loading={busy === "tpl"}>Save templates</Button>
          </form>
        </Card>
      </div>}
    </>
  );
}
