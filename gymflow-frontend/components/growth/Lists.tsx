"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { percent } from "@/components/shared/growth";
import { Badge, EmptyState } from "@/components/shared/ui";
import { formatCurrency, humanize } from "@/lib/utils";

export interface Action { key: string; title: string; count: number; href: string; priority: string; detail: string }
export interface Recommendation { id: string; title: string; detail: string; priority: string; href: string; module: string; evidence: { label: string; value: number | string; kind?: string }[] }

export function ActionList({ actions }: { actions: Action[] }) {
  if (!actions.length) return <EmptyState title="All clear" description="Nothing needs attention right now." />;
  return (
    <ul className="divide-y divide-border/60">
      {actions.map((a) => (
        <li key={a.key}>
          <Link href={a.href} className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-surface-2">
            <span className={`h-2 w-2 shrink-0 rounded-full ${a.priority === "high" ? "bg-danger" : a.priority === "medium" ? "bg-warning" : "bg-muted"}`} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="font-medium">{a.title}</p>
              <p className="truncate text-xs text-muted">{a.detail}</p>
            </div>
            <span className="text-xs text-muted">{humanize(a.priority)}</span>
            <ArrowRight className="h-4 w-4 text-muted" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function RecommendationList({ items, currency = "INR" }: { items: Recommendation[]; currency?: string }) {
  if (!items.length) return <EmptyState title="No recommendations" description="Your data doesn't show anything urgent." />;
  return (
    <ul className="divide-y divide-border/60">
      {items.map((r) => (
        <li key={r.id} className="px-4 py-3">
          <div className="flex items-start justify-between gap-3">
            <Link href={r.href} className="text-sm font-medium hover:text-brand">{r.title}</Link>
            <Badge value={r.priority === "high" ? "overdue" : r.priority === "medium" ? "pending" : "draft"} className="shrink-0" />
          </div>
          <p className="mt-0.5 text-xs text-muted">{r.detail}</p>
          {r.evidence.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {r.evidence.map((e) => (
                <span key={e.label} className="text-muted">{e.label}: <span className="font-medium text-fg tabular-nums">
                  {e.kind === "currency" ? formatCurrency(Number(e.value), currency) : e.kind === "currency_estimate" ? `~${formatCurrency(Number(e.value), currency)} (estimate)` : e.kind === "percent" ? percent(Number(e.value)) : e.value}
                </span></span>
              ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

