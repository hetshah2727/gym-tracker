"use client";

import { CheckCircle2, Delete, Lock, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { API_URL, api, post } from "@/services/api";
import { cn, daysPhrase, firstName, formatCurrency, initials } from "@/lib/utils";
import type { Gym, Member, Page } from "@/types";

type Result = { kind: "ok" | "blocked"; member: Member; message: string; sub?: string };
const PIN_KEY = "gf-kiosk-pin";
const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "clear", "0", "back"];

/** Front-desk tablet: members type the last digits of their phone and tap their name to check in. */
export default function KioskPage() {
  const router = useRouter();
  const [gym, setGym] = useState<Gym | null>(null);
  const [pin, setPin] = useState<string | null>(null);
  const [newPin, setNewPin] = useState("");
  const [digits, setDigits] = useState("");
  const [matches, setMatches] = useState<Member[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [exiting, setExiting] = useState(false);
  const [exitPin, setExitPin] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Gym>("/gym").then(setGym).catch(() => setGym(null));
    try { setPin(sessionStorage.getItem(PIN_KEY)); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (digits.length < 4) { setMatches([]); return; }
    const t = setTimeout(() => {
      api<Page<Member>>("/members", { query: { search: digits, limit: 6 } }).then((p) => setMatches(p.items)).catch(() => setMatches([]));
    }, 200);
    return () => clearTimeout(t);
  }, [digits]);

  const reset = useCallback(() => { setDigits(""); setMatches([]); setResult(null); }, []);
  useEffect(() => {
    if (!result) return;
    const t = setTimeout(reset, result.kind === "ok" ? 3500 : 9000);
    return () => clearTimeout(t);
  }, [result, reset]);

  const press = (k: string) => {
    if (result) reset();
    setDigits((d) => (k === "clear" ? "" : k === "back" ? d.slice(0, -1) : d.length < 10 ? d + k : d));
  };

  const checkIn = async (m: Member) => {
    const name = firstName(m.full_name);
    if (m.status !== "active") {
      setResult({ kind: "blocked", member: m, message: `Sorry ${name}, your membership has ended.`,
        sub: "Please renew at the desk to continue training." });
      return;
    }
    setBusy(true);
    try {
      await post("/attendance/check-in", { member_id: m.id, source: "kiosk" });
      setResult({ kind: "ok", member: m, message: `Welcome, ${name}!`,
        sub: m.due_amount ? `${formatCurrency(m.due_amount)} fee due – please pay at the desk.` : m.days_left != null ? `Membership: ${daysPhrase(m.days_left)}` : undefined });
    } catch {
      setResult({ kind: "blocked", member: m, message: `Sorry ${name}, we couldn't check you in.`,
        sub: "Please ask at the desk." });
    } finally {
      setBusy(false);
    }
  };

  const upi = gym?.settings?.upi_id ? String(gym.settings.upi_id) : null;
  const qrFor = (m: Member) => gym && upi && (m.due_amount || (m.days_left ?? 0) < 0)
    ? `${API_URL}/public/sites/${gym.slug}/pay/qr.svg?amount=${Math.round(m.due_amount || 0) || ""}&note=${encodeURIComponent(`${gym.name} - ${m.full_name}`.slice(0, 60))}` : null;

  if (pin === null) {
    return (
      <main className="flex min-h-screen items-center justify-center p-6">
        <form className="card w-full max-w-sm space-y-4 p-6 text-center" onSubmit={(e) => {
          e.preventDefault();
          try { sessionStorage.setItem(PIN_KEY, newPin); } catch { /* ignore */ }
          setPin(newPin);
          document.documentElement.requestFullscreen?.().catch(() => {});
        }}>
          <Lock className="mx-auto h-8 w-8 text-brand" />
          <h1 className="font-display text-xl font-bold">Start check-in kiosk</h1>
          <p className="text-sm text-muted">Set a 4-digit PIN. Staff need it to leave kiosk mode, so members can only check in.</p>
          <input className="input text-center text-2xl tracking-[0.5em]" inputMode="numeric" maxLength={4} required pattern="\d{4}"
            value={newPin} onChange={(e) => setNewPin(e.target.value.replace(/\D/g, ""))} aria-label="Kiosk PIN" />
          <button className="w-full rounded-xl bg-brand py-3 font-semibold text-brand-fg">Start kiosk</button>
        </form>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col bg-bg p-4 sm:p-8">
      <header className="flex items-center justify-between">
        <p className="font-display text-xl font-extrabold">{gym?.name ?? "Check in"}</p>
        <button onClick={() => setExiting(true)} className="rounded-lg p-2 text-muted" aria-label="Exit kiosk"><Lock className="h-5 w-5" /></button>
      </header>

      <div className="mx-auto mt-6 grid w-full max-w-4xl flex-1 gap-8 lg:grid-cols-2">
        <section className="flex flex-col">
          <p className="text-center text-lg text-muted">Type the last digits of your phone number</p>
          <p className="num my-4 h-16 text-center font-display text-5xl font-extrabold tracking-[0.2em]">{digits || <span className="text-muted/40">••••</span>}</p>
          <div className="grid grid-cols-3 gap-3">
            {KEYS.map((k) => (
              <button key={k} onClick={() => press(k)} aria-label={k === "back" ? "Delete" : k === "clear" ? "Clear" : k}
                className={cn("flex h-20 items-center justify-center rounded-2xl text-3xl font-bold transition active:scale-95",
                  k === "clear" || k === "back" ? "bg-surface-2 text-lg text-muted" : "card shadow-sm")}>
                {k === "back" ? <Delete className="h-7 w-7" /> : k === "clear" ? "Clear" : k}
              </button>
            ))}
          </div>
        </section>

        <section className="flex flex-col justify-center">
          {result ? (
            <div className={cn("card animate-rise p-8 text-center", result.kind === "ok" ? "border-money/50" : "border-danger/50")}>
              {result.kind === "ok" ? <CheckCircle2 className="mx-auto h-16 w-16 text-money" /> : <XCircle className="mx-auto h-16 w-16 text-danger" />}
              <p className="mt-4 font-display text-3xl font-extrabold">{result.message}</p>
              {result.sub && <p className={cn("mt-2 text-lg", result.member.due_amount || result.kind === "blocked" ? "text-danger" : "text-muted")}>{result.sub}</p>}
              {qrFor(result.member) && (
                <div className="mt-5">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={qrFor(result.member)!} alt="UPI QR code to pay" className="mx-auto h-44 w-44 rounded-xl bg-white p-2" />
                  <p className="mt-2 text-sm text-muted">Scan with any UPI app to pay</p>
                </div>
              )}
            </div>
          ) : digits.length < 4 ? (
            <p className="text-center text-muted">Your name will appear here</p>
          ) : matches.length === 0 ? (
            <p className="text-center text-muted">No member found. Please check the number or ask at the desk.</p>
          ) : (
            <ul className="space-y-3">
              {matches.map((m) => (
                <li key={m.id}>
                  <button disabled={busy} onClick={() => checkIn(m)} className="card flex w-full items-center gap-4 p-5 text-left transition hover:shadow-soft active:scale-[0.99]">
                    <span className="flex h-14 w-14 items-center justify-center rounded-full bg-brand/10 text-lg font-bold text-brand">{initials(m.full_name)}</span>
                    <span className="flex-1">
                      <span className="block font-display text-2xl font-bold">{m.full_name}</span>
                      <span className="text-muted">•••• {m.phone.slice(-4)}</span>
                    </span>
                    <span className="rounded-xl bg-brand px-4 py-2 font-semibold text-brand-fg">Check in</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {exiting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setExiting(false)}>
          <form className="card w-full max-w-xs space-y-3 p-6 text-center" onClick={(e) => e.stopPropagation()} onSubmit={(e) => {
            e.preventDefault();
            if (exitPin === pin) {
              try { sessionStorage.removeItem(PIN_KEY); } catch { /* ignore */ }
              document.exitFullscreen?.().catch(() => {});
              router.push("/dashboard/attendance");
            } else setExitPin("");
          }}>
            <p className="font-semibold">Enter the kiosk PIN to exit</p>
            <input autoFocus className="input text-center text-2xl tracking-[0.5em]" inputMode="numeric" maxLength={4}
              value={exitPin} onChange={(e) => setExitPin(e.target.value.replace(/\D/g, ""))} aria-label="Kiosk PIN" />
            <button className="w-full rounded-xl bg-fg py-2.5 font-semibold text-bg">Exit</button>
          </form>
        </div>
      )}
    </main>
  );
}
