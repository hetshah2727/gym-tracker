"use client";

import {
  Activity, BarChart3, Bot, BrainCircuit, CalendarCheck, CalendarClock, CalendarX, CircleDollarSign, ClipboardList,
  CreditCard, FileBarChart, FileSearch, Gauge, Globe, HandCoins, History, IdCard, Inbox, KanbanSquare, KeyRound,
  LayoutDashboard, LineChart, ListChecks, MapPin, Megaphone, MessageCircle, MessagesSquare, PlugZap, Receipt,
  RefreshCcw, ScanSearch, Settings, ShoppingBag, Sparkles, Star, Store, Target, Ticket, TrendingUp, UserCog,
  UserX, Users, Utensils, Wallet, Workflow,
} from "lucide-react";
import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { AppShell, type NavItem, type NavSection } from "@/components/dashboard/AppShell";
import { EntitlementsProvider, ToastProvider, useEntitlements } from "@/components/shared/growth";
import { Loading } from "@/components/shared/ui";
import { getRole } from "@/services/api";
import { getActingGymId } from "@/services/tenant";

type Item = NavItem & { feature?: string };
type Section = { title?: string; items: Item[]; collapsed?: boolean };

const OWNER_NAV: Section[] = [
  {
    title: "Growth dashboard",
    items: [
      { href: "/dashboard/overview", label: "Overview", icon: LayoutDashboard },
      { href: "/dashboard/actions", label: "Today's actions", icon: ListChecks },
      { href: "/dashboard/recovery?tab=opportunities", label: "Revenue opportunities", icon: Target, feature: "recovery_center" },
      { href: "/dashboard/assistant", label: "AI growth assistant", icon: Sparkles, feature: "business_analyst" },
    ],
  },
  {
    title: "SEO & visibility",
    items: [
      { href: "/dashboard/seo", label: "Website SEO", icon: Globe, feature: "seo_audit" },
      { href: "/dashboard/seo?tab=audits", label: "SEO audits", icon: FileSearch, feature: "seo_audit" },
      { href: "/dashboard/seo/keywords", label: "Keywords", icon: KeyRound, feature: "seo_audit" },
      { href: "/dashboard/seo/landing-pages", label: "Landing pages", icon: Store, feature: "website_builder" },
      { href: "/dashboard/local", label: "Google Maps SEO", icon: MapPin, feature: "local_seo" },
      { href: "/dashboard/local?tab=profile", label: "Business profile", icon: IdCard, feature: "local_seo" },
      { href: "/dashboard/local/reviews", label: "Reviews", icon: Star, feature: "local_seo" },
      { href: "/dashboard/local/competitors", label: "Local competitors", icon: ScanSearch, feature: "local_seo" },
      { href: "/dashboard/ai-search", label: "AI search visibility", icon: BrainCircuit, feature: "ai_search_readiness" },
      { href: "/dashboard/ai-search?tab=readiness", label: "GPT readiness", icon: Gauge, feature: "ai_search_readiness" },
    ],
  },
  {
    title: "Leads & sales",
    items: [
      { href: "/dashboard/sales-agent", label: "AI sales agent", icon: Bot, feature: "ai_sales_agent" },
      { href: "/dashboard/leads", label: "Lead inbox", icon: Inbox, feature: "lead_crm" },
      { href: "/dashboard/pipeline", label: "Sales pipeline", icon: KanbanSquare, feature: "lead_crm" },
      { href: "/dashboard/follow-ups", label: "Follow-ups", icon: ClipboardList, feature: "lead_crm" },
      { href: "/dashboard/lead-sources", label: "Lead sources", icon: Megaphone, feature: "lead_crm" },
      { href: "/dashboard/sales-analytics", label: "Sales analytics", icon: TrendingUp, feature: "lead_crm" },
    ],
  },
  {
    title: "Trial management",
    items: [
      { href: "/dashboard/trials", label: "Trial calendar", icon: CalendarClock, feature: "trials" },
      { href: "/dashboard/trials?tab=bookings", label: "Trial bookings", icon: CalendarCheck, feature: "trials" },
      { href: "/dashboard/trials?tab=no-shows", label: "No-shows", icon: CalendarX, feature: "trials" },
      { href: "/dashboard/trials?tab=conversion", label: "Trial conversion", icon: Activity, feature: "trials" },
    ],
  },
  {
    title: "Revenue recovery",
    items: [
      { href: "/dashboard/recovery", label: "Membership renewals", icon: RefreshCcw, feature: "recovery_center" },
      { href: "/dashboard/recovery?tab=outstanding", label: "Outstanding payments", icon: Wallet, feature: "recovery_center" },
      { href: "/dashboard/recovery?tab=failed", label: "Failed payments", icon: Receipt, feature: "recovery_center" },
      { href: "/dashboard/recovery?tab=opportunities", label: "Recovery opportunities", icon: HandCoins, feature: "recovery_center" },
      { href: "/dashboard/recovery?tab=history", label: "Recovery history", icon: History, feature: "recovery_center" },
    ],
  },
  {
    title: "AI business intelligence",
    items: [
      { href: "/dashboard/assistant", label: "Business analyst", icon: BrainCircuit, feature: "business_analyst" },
      { href: "/dashboard/revenue", label: "Revenue analytics", icon: CircleDollarSign, feature: "basic_reports" },
      { href: "/dashboard/sales-analytics", label: "Lead analytics", icon: LineChart, feature: "lead_crm" },
      { href: "/dashboard/reports?kind=seo", label: "SEO reports", icon: FileBarChart, feature: "seo_audit" },
      { href: "/dashboard/reports", label: "Growth reports", icon: BarChart3, feature: "basic_reports" },
    ],
  },
  {
    title: "Automation & integrations",
    collapsed: true,
    items: [
      { href: "/dashboard/integrations?tab=whatsapp", label: "WhatsApp", icon: MessageCircle },
      { href: "/dashboard/ai-settings", label: "AI settings", icon: Bot },
      { href: "/dashboard/workflows", label: "Workflow center", icon: Workflow },
      { href: "/dashboard/integrations", label: "Integration health", icon: PlugZap },
      { href: "/dashboard/automation", label: "Notification settings", icon: MessagesSquare, feature: "automation" },
    ],
  },
  {
    title: "Gym management",
    collapsed: true,
    items: [
      { href: "/dashboard/members", label: "Members", icon: Users },
      { href: "/dashboard/memberships", label: "Membership plans", icon: Ticket },
      { href: "/dashboard/attendance", label: "Attendance", icon: CalendarCheck },
      { href: "/dashboard/trainers", label: "Trainers & staff", icon: UserCog },
      { href: "/dashboard/payments", label: "Payments", icon: CreditCard },
      { href: "/dashboard/gym-profile", label: "Gym profile & knowledge", icon: IdCard },
      { href: "/dashboard/website-builder", label: "Website builder", icon: Globe, feature: "website_builder" },
      { href: "/dashboard/member-portal", label: "Member portal", icon: UserX },
    ],
  },
  {
    title: "More",
    collapsed: true,
    items: [
      { href: "/dashboard/diet-plans", label: "AI nutrition (optional)", icon: Utensils, feature: "ai_diet" },
      { href: "/dashboard/affiliate", label: "Affiliate store (legacy)", icon: ShoppingBag, feature: "affiliate" },
      { href: "/dashboard/analytics", label: "Classic reports", icon: BarChart3 },
      { href: "/dashboard/plan", label: "Plan & usage", icon: Gauge },
      { href: "/dashboard/settings", label: "Settings", icon: Settings },
    ],
  },
];

const TRAINER_NAV: Section[] = [
  {
    items: [
      { href: "/dashboard/members", label: "My members", icon: Users },
      { href: "/dashboard/trials", label: "Trials", icon: CalendarClock, feature: "trials" },
      { href: "/dashboard/follow-ups", label: "My tasks", icon: ClipboardList },
      { href: "/dashboard/attendance", label: "Attendance", icon: CalendarCheck },
      { href: "/dashboard/diet-plans", label: "Diet plans", icon: Utensils },
    ],
  },
];

function Shell({ role, children }: { role: string | null; children: React.ReactNode }) {
  const { ent } = useEntitlements();
  const sections: NavSection[] = useMemo(() => {
    const base = role === "trainer" ? TRAINER_NAV : OWNER_NAV;
    return base.map((s) => ({
      ...s,
      items: s.items
        .filter((i) => !(role === "gym_manager" && ["/dashboard/plan"].includes(i.href)))
        .map(({ feature, ...i }) => ({ ...i, locked: Boolean(feature && ent && ent.features[feature] === false) })),
    }));
  }, [role, ent]);
  const [acting, setActing] = useState<string | null>(null);
  useEffect(() => setActing(getActingGymId()), []);
  const trialBanner = ent && ent.status === "trial_expired" ? (
    <div className="border-b border-danger/30 bg-danger/10 px-4 py-2 text-center text-xs text-danger">
      Your trial has ended - growth features are paused. <Link href="/dashboard/plan" className="underline">Choose a plan</Link>
    </div>
  ) : null;
  const banner = role === "platform_admin" ? (
    <div className="border-b border-warning/30 bg-warning/10 px-4 py-2 text-center text-xs text-warning">
      {acting ? "You are viewing a gym as platform admin." : "Pick a gym to view from the admin console."}{" "}
      <Link href="/platform/admin/gyms" className="underline">Back to admin</Link>
    </div>
  ) : trialBanner;
  return (
    <AppShell sections={sections} subtitle={role === "trainer" ? "Trainer" : "Revenue growth engine"} banner={banner}>
      <Suspense fallback={<Loading />}>{children}</Suspense>
    </AppShell>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState<string | null>(null);
  useEffect(() => setRole(getRole()), []);
  return (
    <ToastProvider>
      <EntitlementsProvider enabled={role !== null && role !== "platform_admin"}>
        <Shell role={role}>{children}</Shell>
      </EntitlementsProvider>
    </ToastProvider>
  );
}
