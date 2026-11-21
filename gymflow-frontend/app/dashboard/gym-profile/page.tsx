"use client";

import { CheckCircle2, Plus, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Note, useAction } from "@/components/shared/growth";
import { Button, Card, Field, Input, Loading, PageHeader, Textarea } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { useRole } from "@/hooks/useRole";
import { formatDateTime } from "@/lib/utils";
import { post, put } from "@/services/api";

interface Profile {
  business_name: string | null; website_url: string | null; description: string | null; address_line: string | null; area: string | null; city: string | null; state: string | null; postal_code: string | null;
  phone: string | null; whatsapp: string | null; email: string | null; opening_hours: { days: string; opens: string; closes: string }[]; services: string[]; facilities: string[]; service_areas: string[];
  target_audience: string[]; social_profiles: Record<string, string>; trial_offer: { enabled?: boolean; price?: number; duration_minutes?: number; notes?: string }; rules: string | null;
  faqs: { q: string; a: string; approved: boolean }[]; review_url: string | null; approved_at: string | null;
}
const LISTS = [["services", "Services"], ["facilities", "Facilities"], ["service_areas", "Service areas (real neighbourhoods you serve)"], ["target_audience", "Who it's for"]] as const;

export default function GymProfilePage() {
  const { data, loading, reload } = useApi<Profile>("/gym-profile");
  const role = useRole();
  const [p, setP] = useState<Profile | null>(null);
  const { busy, run } = useAction();
  useEffect(() => { if (data) setP(data); }, [data]);
  if (loading || !p) return <Loading />;
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setP({ ...p, [k]: v });
  const save = () => run("save", () => put<Profile>("/gym-profile", { ...p, email: p.email || null, approved_at: undefined }), "Profile saved - approve it so agents treat it as approved").then((r) => r && setP(r));

  return (
    <>
      <PageHeader title="Gym profile & knowledge base" description="The approved facts about your gym. The AI sales agent, website content, landing pages and structured data only use what is here (plus your live plans and trainers)."
        actions={<><Button loading={busy === "save"} onClick={save}>Save</Button>
          {role === "gym_owner" && <Button variant="secondary" loading={busy === "ok"} onClick={() => run("ok", () => post<Profile>("/gym-profile/approve"), "Approved").then(() => reload())}><CheckCircle2 className="h-4 w-4" /> Approve</Button>}</>} />
      <Note tone={p.approved_at ? "success" : "warning"} className="mb-4">{p.approved_at ? `Approved ${formatDateTime(p.approved_at)}.` : "Not approved since the last change. Review and approve it (owner)."} Prices come from Membership plans, and coaches from Trainers.</Note>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Business identity"><div className="grid gap-3 p-4 sm:grid-cols-2">
          {([["business_name", "Business name (exact, no keywords)"], ["website_url", "Website"], ["phone", "Phone"], ["whatsapp", "WhatsApp"], ["email", "Email"], ["review_url", "Google review link"]] as const).map(([k, l]) =>
            <Field key={k} label={l}><Input value={(p[k] as string) ?? ""} onChange={(e) => set(k, e.target.value)} /></Field>)}
          <Field label="Description" className="sm:col-span-2"><Textarea rows={4} value={p.description ?? ""} onChange={(e) => set("description", e.target.value)} /></Field>
        </div></Card>
        <Card title="Location"><div className="grid gap-3 p-4 sm:grid-cols-2">
          <Field label="Street address" className="sm:col-span-2"><Input value={p.address_line ?? ""} onChange={(e) => set("address_line", e.target.value)} /></Field>
          {([["area", "Area / neighbourhood"], ["city", "City"], ["state", "State"], ["postal_code", "PIN code"]] as const).map(([k, l]) => <Field key={k} label={l}><Input value={(p[k] as string) ?? ""} onChange={(e) => set(k, e.target.value)} /></Field>)}
        </div></Card>
        <Card title="Opening hours"><div className="space-y-2 p-4">
          {p.opening_hours.map((h, i) => (
            <div key={i} className="flex gap-2">
              <Input value={h.days} onChange={(e) => set("opening_hours", p.opening_hours.map((x, j) => (j === i ? { ...x, days: e.target.value } : x)))} placeholder="Mon-Sat" />
              <Input type="time" value={h.opens} onChange={(e) => set("opening_hours", p.opening_hours.map((x, j) => (j === i ? { ...x, opens: e.target.value } : x)))} />
              <Input type="time" value={h.closes} onChange={(e) => set("opening_hours", p.opening_hours.map((x, j) => (j === i ? { ...x, closes: e.target.value } : x)))} />
              <Button variant="ghost" aria-label="Remove" onClick={() => set("opening_hours", p.opening_hours.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button>
            </div>))}
          <Button size="sm" variant="secondary" onClick={() => set("opening_hours", [...p.opening_hours, { days: "Mon-Sat", opens: "06:00", closes: "22:00" }])}><Plus className="h-4 w-4" /> Add hours</Button>
        </div></Card>
        <Card title="Services, facilities & areas"><div className="space-y-3 p-4">
          {LISTS.map(([k, l]) => <Field key={k} label={l} hint="Comma separated"><Input value={(p[k] as string[]).join(", ")} onChange={(e) => set(k, e.target.value.split(",").map((x) => x.trimStart()) as never)} onBlur={(e) => set(k, e.target.value.split(",").map((x) => x.trim()).filter(Boolean) as never)} /></Field>)}
        </div></Card>
        <Card title="Trial offer & rules"><div className="space-y-3 p-4">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!p.trial_offer.enabled} onChange={(e) => set("trial_offer", { ...p.trial_offer, enabled: e.target.checked })} /> Offer a trial session</label>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Trial price (₹, 0 = free)"><Input type="number" min={0} value={p.trial_offer.price ?? 0} onChange={(e) => set("trial_offer", { ...p.trial_offer, price: Number(e.target.value) })} /></Field>
            <Field label="Duration (minutes)"><Input type="number" min={15} value={p.trial_offer.duration_minutes ?? 60} onChange={(e) => set("trial_offer", { ...p.trial_offer, duration_minutes: Number(e.target.value) })} /></Field>
          </div>
          <Field label="Gym rules"><Textarea value={p.rules ?? ""} onChange={(e) => set("rules", e.target.value)} /></Field>
        </div></Card>
        <Card title="FAQs" actions={<Button size="sm" variant="secondary" loading={busy === "faq"} onClick={() => run("faq", () => post<{ faqs: Profile["faqs"] }>("/gym-profile/faqs/generate"), "Drafts added - edit and approve them").then((r) => r && set("faqs", [...p.faqs, ...r.faqs]))}><Sparkles className="h-4 w-4" /> Draft FAQs</Button>}>
          <div className="space-y-3 p-4">
            {p.faqs.map((f, i) => (
              <div key={i} className="space-y-1 rounded-lg border border-border p-2">
                <Input value={f.q} onChange={(e) => set("faqs", p.faqs.map((x, j) => (j === i ? { ...x, q: e.target.value } : x)))} />
                <Textarea value={f.a} onChange={(e) => set("faqs", p.faqs.map((x, j) => (j === i ? { ...x, a: e.target.value } : x)))} />
                <div className="flex justify-between">
                  <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={f.approved} onChange={(e) => set("faqs", p.faqs.map((x, j) => (j === i ? { ...x, approved: e.target.checked } : x)))} /> Approved for the AI agent & website</label>
                  <button aria-label="Delete FAQ" className="text-muted hover:text-danger" onClick={() => set("faqs", p.faqs.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>))}
            <Button size="sm" variant="secondary" onClick={() => set("faqs", [...p.faqs, { q: "", a: "", approved: false }])}><Plus className="h-4 w-4" /> Add FAQ</Button>
          </div>
        </Card>
      </div>
      <div className="mt-4 flex justify-end"><Button loading={busy === "save"} onClick={save}>Save profile</Button></div>
    </>
  );
}
