"use client";

import { ArrowLeft, ArrowRight, Check, MessageCircle, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ImportMembers } from "@/components/members/ImportMembers";
import { useAction } from "@/components/shared/growth";
import { Button, Card, Field, Input, Loading } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { cn, formatCurrency } from "@/lib/utils";
import { patch, post } from "@/services/api";
import type { Gym, MembershipPlan } from "@/types";

const STEPS = ["Your gym", "Your plans", "Your members", "Reminders", "Done"];

function Stepper({ step }: { step: number }) {
  return (
    <ol className="mb-8 flex items-center gap-2" aria-label="Setup steps">
      {STEPS.map((s, i) => (
        <li key={s} className="flex flex-1 items-center gap-2">
          <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold",
            i < step ? "bg-money text-white" : i === step ? "bg-brand text-brand-fg" : "bg-surface-2 text-muted")}
            aria-current={i === step ? "step" : undefined}>
            {i < step ? <Check className="h-4 w-4" /> : i + 1}
          </span>
          <span className={cn("hidden text-sm sm:block", i === step ? "font-semibold" : "text-muted")}>{s}</span>
          {i < STEPS.length - 1 && <span className="h-px flex-1 bg-border" />}
        </li>
      ))}
    </ol>
  );
}

function GymStep({ next }: { next: () => void }) {
  const { data: gym } = useApi<Gym>("/gym");
  const [form, setForm] = useState({ name: "", phone: "", address: "", city: "", upi_id: "" });
  const { busy, run } = useAction();
  useEffect(() => {
    if (gym) setForm({ name: gym.name, phone: gym.phone ?? "", address: gym.address ?? "", city: gym.city ?? "",
      upi_id: String(gym.settings?.upi_id ?? "") });
  }, [gym]);
  if (!gym) return <Loading />;
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <form className="space-y-4" onSubmit={(e) => {
      e.preventDefault();
      run("gym", () => patch("/gym", { name: form.name, phone: form.phone || null, address: form.address || null, city: form.city || null,
        settings: { upi_id: form.upi_id.trim() || null } })).then((r) => r && next());
    }}>
      <Field label="Gym name"><Input required value={form.name} onChange={set("name")} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Phone (shown to members)"><Input value={form.phone} onChange={set("phone")} inputMode="tel" placeholder="98240 12345" /></Field>
        <Field label="City"><Input value={form.city} onChange={set("city")} placeholder="Vadodara" /></Field>
      </div>
      <Field label="Address"><Input value={form.address} onChange={set("address")} placeholder="Shop 4, Gotri Road" /></Field>
      <Field label="UPI ID for fees (optional)" hint="Added to reminders as a pay-by-UPI page with your QR code, e.g. yourgym@okicici">
        <Input value={form.upi_id} onChange={set("upi_id")} placeholder="yourgym@okicici" pattern="^[\w.\-]{2,256}@[A-Za-z]{2,64}$" />
      </Field>
      <div className="flex justify-end"><Button type="submit" loading={busy === "gym"}>Save and continue <ArrowRight className="h-4 w-4" /></Button></div>
    </form>
  );
}

function PlansStep({ next }: { next: () => void }) {
  const plans = useApi<MembershipPlan[]>("/membership-plans");
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [add, setAdd] = useState({ name: "", duration_days: "30", price: "" });
  const { busy, run } = useAction();
  useEffect(() => {
    if (plans.data) setPrices(Object.fromEntries(plans.data.map((p) => [p.id, String(Math.round(p.price))])));
  }, [plans.data]);
  if (!plans.data) return <Loading />;
  const save = async () => {
    for (const p of plans.data ?? []) {
      const v = Number(prices[p.id]);
      if (Number.isFinite(v) && v !== Math.round(p.price)) await patch(`/membership-plans/${p.id}`, { price: v });
    }
  };
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">We added common plans. Change the prices to what you charge – you can add more any time.</p>
      <ul className="divide-y divide-border/60 rounded-2xl border border-border">
        {plans.data.map((p) => (
          <li key={p.id} className="flex items-center gap-3 px-4 py-3">
            <span className="flex-1"><span className="font-semibold">{p.name}</span> <span className="text-xs text-muted">· {p.duration_days} days</span></span>
            <span className="text-sm text-muted">₹</span>
            <Input className="w-28" inputMode="numeric" value={prices[p.id] ?? ""} onChange={(e) => setPrices({ ...prices, [p.id]: e.target.value.replace(/\D/g, "") })} aria-label={`${p.name} price`} />
          </li>
        ))}
      </ul>
      <form className="grid gap-2 sm:grid-cols-[1fr_110px_120px_auto] sm:items-end" onSubmit={(e) => {
        e.preventDefault();
        run("add", () => post("/membership-plans", { name: add.name, duration_days: Number(add.duration_days), price: Number(add.price) }), "Plan added")
          .then((r) => { if (r) { setAdd({ name: "", duration_days: "30", price: "" }); plans.reload(); } });
      }}>
        <Field label="Another plan"><Input value={add.name} onChange={(e) => setAdd({ ...add, name: e.target.value })} placeholder="e.g. Couple monthly" /></Field>
        <Field label="Days"><Input inputMode="numeric" value={add.duration_days} onChange={(e) => setAdd({ ...add, duration_days: e.target.value.replace(/\D/g, "") })} /></Field>
        <Field label="Price ₹"><Input inputMode="numeric" value={add.price} onChange={(e) => setAdd({ ...add, price: e.target.value.replace(/\D/g, "") })} /></Field>
        <Button type="submit" variant="secondary" disabled={!add.name || !add.price || !add.duration_days} loading={busy === "add"}><Plus className="h-4 w-4" /> Add</Button>
      </form>
      <div className="flex justify-end"><Button loading={busy === "save"} onClick={() => run("save", save).then(next)}>Save and continue <ArrowRight className="h-4 w-4" /></Button></div>
    </div>
  );
}

function MembersStep({ next }: { next: () => void }) {
  const [added, setAdded] = useState<number | null>(null);
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">Bring your members over from your register or Excel. Using Google Sheets? Choose File → Download → CSV first.</p>
      <ImportMembers onDone={setAdded} />
      <div className="flex justify-between">
        <span className="text-xs text-muted">{added === null ? "You can also add members one by one later." : ""}</span>
        <Button variant={added === null ? "secondary" : "primary"} onClick={next}>{added === null ? "Skip for now" : "Continue"} <ArrowRight className="h-4 w-4" /></Button>
      </div>
    </div>
  );
}

function RemindersStep({ next }: { next: () => void }) {
  return (
    <div className="space-y-4">
      <div className="flex gap-4 rounded-2xl bg-money/[0.07] p-5">
        <MessageCircle className="h-6 w-6 shrink-0 text-money" />
        <div>
          <p className="font-semibold">WhatsApp reminders work right away</p>
          <p className="mt-1 text-sm text-muted">When you tap <strong>Remind</strong>, WhatsApp opens on your phone with the message ready – including the amount and a pay link if you added your UPI ID. Nothing to set up.</p>
        </div>
      </div>
      <div className="rounded-2xl border border-border p-5">
        <p className="font-semibold">Want reminders sent automatically?</p>
        <p className="mt-1 text-sm text-muted">Connect the WhatsApp Business API later (Meta approval takes about 1–3 weeks). GymFlow then sends the 30, 15 and 7-day renewal reminders by itself.</p>
        <Link href="/dashboard/integrations?tab=whatsapp" className="mt-2 inline-block text-sm font-semibold text-brand underline">See how to connect</Link>
      </div>
      <div className="flex justify-end"><Button onClick={next}>Continue <ArrowRight className="h-4 w-4" /></Button></div>
    </div>
  );
}

function DoneStep() {
  const { data } = useApi<{ money: { due_total: number; due_count: number } }>("/growth/dashboard");
  return (
    <div className="flex flex-col items-center gap-3 py-6 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-full bg-money text-white"><Check className="h-7 w-7" /></span>
      <h2 className="font-display text-2xl font-bold">Your gym is ready</h2>
      {data && data.money.due_count > 0 ? (
        <p className="max-w-md text-muted">You have <strong className="text-fg">{formatCurrency(data.money.due_total)}</strong> in fees and renewals coming up from {data.money.due_count} members. Let&apos;s remind them.</p>
      ) : <p className="max-w-md text-muted">Every day, GymFlow will show you who to remind and what to do first.</p>}
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        {data && data.money.due_count > 0 && <Link href="/dashboard/money" className="rounded-xl bg-brand px-5 py-3 text-sm font-semibold text-brand-fg">See who owes money</Link>}
        <Link href="/dashboard/overview" className="rounded-xl border border-border px-5 py-3 text-sm font-semibold hover:bg-surface-2">Go to Today</Link>
      </div>
    </div>
  );
}

/** First-run setup: gym → plans → members → reminders → done. Every step can be revisited from Settings. */
export default function SetupPage() {
  const [step, setStep] = useState(0);
  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-display text-2xl font-bold tracking-tight sm:text-[1.7rem]">Set up your gym</h1>
      <p className="mb-6 mt-1 text-sm text-muted">About 10 minutes. You can change everything later.</p>
      <Stepper step={step} />
      <Card className="p-6">
        <h2 className="mb-4 font-display text-lg font-bold">{STEPS[step]}</h2>
        {step === 0 && <GymStep next={next} />}
        {step === 1 && <PlansStep next={next} />}
        {step === 2 && <MembersStep next={next} />}
        {step === 3 && <RemindersStep next={next} />}
        {step === 4 && <DoneStep />}
      </Card>
      {step > 0 && step < 4 && (
        <button onClick={() => setStep(step - 1)} className="mt-4 inline-flex items-center gap-1 text-sm text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" /> Back</button>
      )}
    </div>
  );
}
