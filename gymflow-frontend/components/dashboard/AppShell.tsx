"use client";

import { LogOut, MessageCircle, Moon, Plus, Settings, Sun, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { areaFor, tabMatches, type Area } from "@/components/dashboard/nav";
import { setLang, useT } from "@/lib/i18n";
import { cn, initials } from "@/lib/utils";
import { logout } from "@/services/auth";

export interface QuickAction {
  href: string;
  label: string;
  icon: LucideIcon;
}

const SUPPORT_WHATSAPP = process.env.NEXT_PUBLIC_SUPPORT_WHATSAPP;

function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState("light");
  useEffect(() => setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light"), []);
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("gf-theme", next); } catch { /* private mode */ }
    setTheme(next);
  };
  return [theme, toggle];
}

function Logo({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/icon.svg" alt="" className="h-9 w-9 shrink-0 rounded-xl" />
      <div className="min-w-0">
        <p className="truncate font-display text-[0.95rem] font-bold leading-tight">{title}</p>
        {subtitle && <p className="truncate text-xs text-muted">{subtitle}</p>}
      </div>
    </div>
  );
}

function Count({ n, className }: { n?: number; className?: string }) {
  if (!n) return null;
  return (
    <span className={cn("num min-w-[1.25rem] rounded-full bg-brand px-1.5 text-center text-[11px] font-bold leading-5 text-brand-fg", className)}>
      {n > 99 ? "99+" : n}
    </span>
  );
}

export function AppShell({
  areas,
  footerArea,
  title,
  subtitle,
  userName,
  badges,
  isHidden,
  quickActions,
  banner,
  children,
}: {
  areas: Area[];
  footerArea?: Area;
  title: string;
  subtitle?: string;
  userName?: string | null;
  badges?: Partial<Record<"money" | "enquiries", number>>;
  /** Tabs whose feature is not in the plan and that should disappear rather than show a lock. */
  isHidden?: (feature?: string) => boolean;
  quickActions?: QuickAction[];
  banner?: ReactNode;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const [theme, toggleTheme] = useTheme();
  const { t, lang } = useT();
  const langButton = (
    <button onClick={() => setLang(lang === "hi" ? "en" : "hi")} className="rounded-lg px-1.5 py-1 text-xs font-bold text-muted hover:bg-surface-2 hover:text-fg"
      aria-label={lang === "hi" ? "Switch to English" : "हिंदी में देखें"} title={lang === "hi" ? "English" : "हिंदी"}>
      {lang === "hi" ? "EN" : "हिं"}
    </button>
  );
  const [quickOpen, setQuickOpen] = useState(false);
  const all = footerArea ? [...areas, footerArea] : areas;
  const current = areaFor(pathname, all);
  const tabs = (current?.tabs ?? []).filter((t) => !(t.hideIfLocked && isHidden?.(t.feature)));

  useEffect(() => setQuickOpen(false), [pathname]);

  const navLink = (area: Area) => {
    const active = current?.key === area.key;
    const Icon = area.icon;
    return (
      <Link key={area.key} href={area.href} aria-current={active ? "page" : undefined}
        className={cn("group flex items-center gap-3 rounded-xl px-3 py-2.5 text-[0.95rem] transition",
          active ? "bg-fg text-bg font-semibold" : "text-muted hover:bg-surface-2 hover:text-fg")}>
        <Icon className="h-[18px] w-[18px]" strokeWidth={active ? 2.4 : 2} />
        <span className="flex-1">{t(area.label)}</span>
        <Count n={area.badge ? badges?.[area.badge] : undefined} className={active ? "bg-bg text-fg" : undefined} />
      </Link>
    );
  };

  return (
    <div className="min-h-screen">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r border-border/70 bg-surface lg:flex">
        <div className="px-4 py-5"><Logo title={title} subtitle={subtitle} /></div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3" aria-label="Main">{areas.map(navLink)}</nav>
        <div className="space-y-1 border-t border-border/70 p-3">
          {footerArea && navLink(footerArea)}
          {SUPPORT_WHATSAPP && (
            <a href={`https://wa.me/${SUPPORT_WHATSAPP}`} target="_blank" rel="noreferrer"
              className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-[0.95rem] text-muted hover:bg-surface-2 hover:text-fg">
              <MessageCircle className="h-[18px] w-[18px]" /> {t("Help on WhatsApp")}
            </a>
          )}
          <div className="mt-2 flex items-center gap-2 rounded-xl px-2 py-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-2 text-xs font-bold">{initials(userName || title)}</span>
            <span className="min-w-0 flex-1 truncate text-sm font-medium">{userName || "Account"}</span>
            {langButton}
            <button onClick={toggleTheme} className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-fg" aria-label="Switch light or dark mode">
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button onClick={logout} className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-fg" aria-label="Log out">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <div className="lg:pl-64">
        {/* Mobile top bar */}
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border/70 bg-bg/90 px-4 py-3 backdrop-blur lg:hidden">
          <div className="min-w-0 flex-1"><Logo title={title} /></div>
          {langButton}
          <button onClick={toggleTheme} className="rounded-lg p-2 text-muted" aria-label="Switch light or dark mode">
            {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </button>
          {footerArea && <Link href={footerArea.href} className="rounded-lg p-2 text-muted" aria-label="Settings"><Settings className="h-5 w-5" /></Link>}
          <button onClick={logout} className="rounded-lg p-2 text-muted" aria-label="Log out"><LogOut className="h-5 w-5" /></button>
        </header>
        {banner}
        <main className="mx-auto max-w-6xl px-4 pb-28 pt-5 sm:px-6 lg:px-10 lg:pb-12 lg:pt-8">
          {tabs.length > 1 && (
            <div className="scrollbar-none -mx-4 mb-6 flex gap-1 overflow-x-auto border-b border-border/70 px-4 sm:mx-0 sm:px-0" role="tablist" aria-label={current?.label}>
              {tabs.map((tab) => {
                const active = tabMatches(pathname, tab);
                return (
                  <Link key={tab.href} href={tab.href} role="tab" aria-selected={active}
                    className={cn("-mb-px whitespace-nowrap border-b-2 px-3 pb-2.5 pt-1 text-sm transition",
                      active ? "border-brand font-semibold text-fg" : "border-transparent text-muted hover:text-fg")}>
                    {t(tab.label)}
                  </Link>
                );
              })}
            </div>
          )}
          {children}
        </main>
      </div>

      {/* Mobile bottom tab bar */}
      <nav className="pb-safe fixed inset-x-0 bottom-0 z-40 border-t border-border/70 bg-surface/95 backdrop-blur lg:hidden" aria-label="Main">
        <div className="mx-auto flex max-w-lg">
          {areas.slice(0, 5).map((area) => {
            const active = current?.key === area.key;
            const Icon = area.icon;
            const n = area.badge ? badges?.[area.badge] : undefined;
            return (
              <Link key={area.key} href={area.href} aria-current={active ? "page" : undefined}
                className={cn("relative flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[11px]", active ? "font-semibold text-brand" : "text-muted")}>
                <Icon className="h-5 w-5" strokeWidth={active ? 2.4 : 2} />
                {t(area.label)}
                {!!n && <span className="absolute right-[calc(50%-18px)] top-1.5 h-2 w-2 rounded-full bg-brand" aria-label={`${n} waiting`} />}
              </Link>
            );
          })}
        </div>
      </nav>

      {/* Quick add */}
      {quickActions && quickActions.length > 0 && (
        <div className="fixed bottom-20 right-4 z-40 flex flex-col items-end gap-2 lg:bottom-6 lg:right-6">
          {quickOpen && (
            <div className="card flex animate-rise flex-col p-1.5 shadow-soft">
              {quickActions.map((q) => (
                <Link key={q.href} href={q.href} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium hover:bg-surface-2">
                  <q.icon className="h-4 w-4 text-brand" /> {t(q.label)}
                </Link>
              ))}
            </div>
          )}
          <button onClick={() => setQuickOpen((o) => !o)} aria-expanded={quickOpen} aria-label={quickOpen ? "Close quick actions" : "Quick actions"}
            className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand text-brand-fg shadow-soft transition hover:bg-brand/90">
            {quickOpen ? <X className="h-6 w-6" /> : <Plus className="h-6 w-6" />}
          </button>
        </div>
      )}
    </div>
  );
}
