"use client";

import { useState } from "react";
import { formatCurrency } from "@/lib/utils";

const PLAN_PRICE = 2499;

function Slider({ label, value, min, max, step, format, onChange }: {
  label: string; value: number; min: number; max: number; step: number; format: (v: number) => string; onChange: (v: number) => void;
}) {
  return (
    <label className="block">
      <span className="flex justify-between text-sm"><span className="text-muted">{label}</span><span className="num font-semibold">{format(value)}</span></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 w-full accent-[rgb(var(--brand))]" />
    </label>
  );
}

/** A transparent back-of-the-envelope estimate. Every input is visible and the maths is shown. */
export function RoiCalculator() {
  const [members, setMembers] = useState(250);
  const [fee, setFee] = useState(1500);
  const [late, setLate] = useState(15);
  const atRisk = Math.round(members * fee * (late / 100));
  const half = Math.round(atRisk / 2);

  return (
    <div className="card grid gap-8 p-6 shadow-soft sm:p-8 md:grid-cols-2">
      <div className="space-y-6">
        <Slider label="Members" value={members} min={50} max={1500} step={10} format={(v) => String(v)} onChange={setMembers} />
        <Slider label="Average monthly fee" value={fee} min={500} max={5000} step={100} format={(v) => formatCurrency(v)} onChange={setFee} />
        <Slider label="Members who pay late or forget to renew each month" value={late} min={5} max={40} step={1} format={(v) => `${v}%`} onChange={setLate} />
      </div>
      <div className="flex flex-col justify-center rounded-2xl bg-surface-2 p-6">
        <p className="text-sm text-muted">Fees at risk every month</p>
        <p className="num font-display text-4xl font-extrabold">{formatCurrency(atRisk)}</p>
        <p className="mt-4 text-sm text-muted">If timely WhatsApp reminders bring back just half of it</p>
        <p className="num font-display text-4xl font-extrabold text-money">{formatCurrency(half)}<span className="text-base font-semibold text-muted"> / month</span></p>
        <p className="mt-4 text-sm">
          That&apos;s <strong>{Math.max(1, Math.round(half / PLAN_PRICE))}×</strong> the Growth plan ({formatCurrency(PLAN_PRICE)}/month).
        </p>
        <p className="mt-3 text-xs text-muted">An estimate from your numbers: members × fee × % late ÷ 2. Once you&apos;re on GymFlow, it shows the real amount it brought back every month.</p>
      </div>
    </div>
  );
}
