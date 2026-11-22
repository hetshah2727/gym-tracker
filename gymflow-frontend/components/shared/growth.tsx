"use client";

import { AlertTriangle, CheckCircle2, Info, Lock, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Button, Modal } from "@/components/shared/ui";
import { cn, humanize } from "@/lib/utils";
import { api } from "@/services/api";

// ---------------------------------------------------------------- data provenance labels

const SOURCE_LABELS: Record<string, { label: string; tone: string; title: string }> = {
  demo_simulated: { label: "Demo data", tone: "bg-warning/15 text-warning", title: "Simulated for the demo – not from a live integration" },
  manual: { label: "Entered manually", tone: "bg-surface-2 text-muted", title: "Typed in by your team" },
  user_supplied: { label: "User-supplied", tone: "bg-surface-2 text-muted", title: "Figures entered by your team" },
  live_search: { label: "Live Google check", tone: "bg-info/10 text-info", title: "Checked with Gemini using live Google Search results" },
  groq: { label: "AI answer", tone: "bg-violet-500/15 text-violet-500", title: "Answered by AI using your GymFlow data" },
  gemini: { label: "AI draft", tone: "bg-violet-500/15 text-violet-500", title: "Written by AI from your approved profile – review before use" },
  manual_research: { label: "Manual research", tone: "bg-surface-2 text-muted", title: "Sampled by hand – not automatic monitoring" },
  google_business_profile: { label: "Google (live)", tone: "bg-sky-500/15 text-sky-400", title: "Synced from Google Business Profile" },
  google_search_console: { label: "Search Console", tone: "bg-sky-500/15 text-sky-400", title: "Synced from Google Search Console" },
  crawl: { label: "Live crawl", tone: "bg-money/10 text-money", title: "Fetched from the website by GymFlow" },
  observed: { label: "Observed", tone: "bg-money/10 text-money", title: "Seen directly on the website" },
  ai: { label: "AI draft", tone: "bg-violet-500/15 text-violet-400", title: "Written by AI from your approved profile – review before use" },
  template: { label: "Template draft", tone: "bg-surface-2 text-muted", title: "Built from your profile by a template – review before use" },
  rule_suggestion: { label: "Suggestion", tone: "bg-surface-2 text-muted", title: "Idea based on your profile – no search-volume data" },
  rules: { label: "Quick answer", tone: "bg-surface-2 text-muted", title: "Answered from your GymFlow data" },
  claude: { label: "AI answer", tone: "bg-violet-500/15 text-violet-500", title: "Answered by AI using your GymFlow data" },
};

export function SourceBadge({ source, className }: { source: string | null | undefined; className?: string }) {
  if (!source) return null;
  const s = SOURCE_LABELS[source] ?? { label: humanize(source), tone: "bg-surface-2 text-muted", title: source };
  return <span title={s.title} className={cn("inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium", s.tone, className)}>{s.label}</span>;
}

export function Note({ tone = "info", children, className }: { tone?: "info" | "warning" | "success"; children: ReactNode; className?: string }) {
  const Icon = tone === "warning" ? AlertTriangle : tone === "success" ? CheckCircle2 : Info;
  return (
    <div className={cn("flex gap-2 rounded-lg border px-3 py-2 text-sm",
      tone === "warning" ? "border-warning/40 bg-warning/10 text-warning" : tone === "success" ? "border-money/40 bg-money/10 text-money" : "border-border bg-surface-2 text-muted", className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------- toasts

type Toast = { id: number; text: string; tone: "success" | "error" };
const ToastCtx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] flex w-[min(92vw,360px)] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={cn("card flex animate-rise items-start gap-2 px-3 py-2.5 text-sm shadow-soft", t.tone === "error" ? "border-danger/50" : "border-money/50")}>
            {t.tone === "error" ? <AlertTriangle className="mt-0.5 h-4 w-4 text-danger" /> : <CheckCircle2 className="mt-0.5 h-4 w-4 text-money" />}
            <span className="flex-1">{t.text}</span>
            <button aria-label="Dismiss" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}><X className="h-4 w-4 text-muted" /></button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

/** Run an API action with a loading flag and success/error toasts. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>, success?: string | ((r: T) => string)): Promise<T | undefined> => {
    setBusy(key);
    try {
      const result = await fn();
      if (success) toast(typeof success === "function" ? success(result) : success);
      return result;
    } catch (e) {
      toast(e instanceof Error ? e.message : "Something went wrong", "error");
      return undefined;
    } finally {
      setBusy(null);
    }
  }, [toast]);
  return { busy, run };
}

// ---------------------------------------------------------------- confirm dialog

export function ConfirmDialog({ open, title, message, confirmLabel = "Confirm", danger, onConfirm, onClose, busy }: {
  open: boolean; title: string; message: ReactNode; confirmLabel?: string; danger?: boolean; busy?: boolean;
  onConfirm: () => void; onClose: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div className="text-sm text-muted">{message}</div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant={danger ? "danger" : "primary"} loading={busy} onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- entitlements

export interface Entitlements {
  plan_code: string | null;
  plan_name: string | null;
  status: string;
  trial_ends_at: string | null;
  features: Record<string, boolean>;
  limits: Record<string, number | null>;
  usage: Record<string, number>;
  catalog: Record<string, { label: string; tier: string }>;
  billing?: { gateway_subscriptions: boolean; note: string };
}

const EntCtx = createContext<{ ent: Entitlements | null; reload: () => void }>({ ent: null, reload: () => {} });

export function EntitlementsProvider({ children, enabled }: { children: ReactNode; enabled: boolean }) {
  const [ent, setEnt] = useState<Entitlements | null>(null);
  const load = useCallback(() => {
    if (!enabled) return;
    api<Entitlements>("/subscriptions/entitlements").then(setEnt).catch(() => setEnt(null));
  }, [enabled]);
  useEffect(load, [load]);
  return <EntCtx.Provider value={{ ent, reload: load }}>{children}</EntCtx.Provider>;
}

export const useEntitlements = () => useContext(EntCtx);

/** Renders children only when the plan includes ``feature``; otherwise an upgrade notice. */
export function FeatureGate({ feature, children }: { feature: string; children: ReactNode }) {
  const { ent } = useEntitlements();
  if (!ent || ent.features[feature] !== false) return <>{children}</>;
  const info = ent.catalog[feature];
  return (
    <div className="card mx-auto mt-10 max-w-lg p-8 text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand/10 text-brand"><Lock className="h-5 w-5" /></div>
      <p className="font-display text-lg font-bold">{info?.label ?? humanize(feature)} comes with the {humanize(info?.tier ?? "growth")} plan</p>
      <p className="mt-1 text-sm text-muted">You&apos;re on {ent.plan_name ?? "no plan yet"}. Upgrade any time – your data stays exactly as it is.</p>
      <Link href="/dashboard/plan" className="mt-5 inline-block rounded-xl bg-brand px-5 py-2.5 text-sm font-semibold text-brand-fg">See plans</Link>
    </div>
  );
}

// ---------------------------------------------------------------- tabs in the URL

export function useQueryTab<T extends string>(fallback: T, key = "tab"): [T, (v: T) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const value = (params.get(key) as T) || fallback;
  const set = (v: T) => {
    const next = new URLSearchParams(params.toString());
    next.set(key, v);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };
  return [value, set];
}

// ---------------------------------------------------------------- tiny markdown (assistant replies)

export function MiniMarkdown({ text }: { text: string }) {
  const inline = (line: string, k: number) => {
    const parts = line.split(/(\*\*[^*]+\*\*|\/dashboard\/[\w\-/?=&.]+)/g);
    return (
      <span key={k}>
        {parts.map((p, i) =>
          p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> :
          p.startsWith("/dashboard/") ? <Link key={i} href={p} className="text-brand underline">{p.replace("/dashboard/", "").split("?")[0].replace(/[-/]/g, " ")}</Link> : p)}
      </span>
    );
  };
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {text.split(/\n{2,}/).map((block, b) => {
        const lines = block.split("\n");
        if (lines.every((l) => /^\s*[-•]\s/.test(l) || !l.trim()))
          return <ul key={b} className="list-disc space-y-1 pl-5">{lines.filter(Boolean).map((l, i) => <li key={i}>{inline(l.replace(/^\s*[-•]\s/, ""), i)}</li>)}</ul>;
        return <p key={b}>{lines.map((l, i) => <span key={i}>{inline(l, i)}{i < lines.length - 1 && <br />}</span>)}</p>;
      })}
    </div>
  );
}

export function Pager({ total, offset, limit, onChange }: { total: number; offset: number; limit: number; onChange: (o: number) => void }) {
  if (total <= limit) return null;
  return (
    <div className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-muted">
      <span>{offset + 1}–{Math.min(offset + limit, total)} of {total}</span>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</Button>
        <Button size="sm" variant="secondary" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</Button>
      </div>
    </div>
  );
}

export function Kpi({ label, value, hint, href, tone }: { label: string; value: ReactNode; hint?: ReactNode; href?: string; tone?: "warning" | "danger" | "brand" }) {
  const body = (
    <div className={cn("card h-full p-4 transition", href && "hover:border-fg/20 hover:shadow-soft")}>
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className={cn("num mt-1.5 font-display text-2xl font-bold", tone === "danger" && "text-danger", tone === "warning" && "text-warning", tone === "brand" && "text-money")}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
  return href ? <Link href={href} className="block">{body}</Link> : body;
}

export function percent(v: number | null | undefined) {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}
