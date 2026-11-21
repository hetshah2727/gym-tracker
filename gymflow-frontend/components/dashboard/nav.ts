import {
  CalendarCheck, ClipboardList, Home, Inbox, IndianRupee, Settings, Sprout, Users, type LucideIcon,
} from "lucide-react";

/**
 * Owner navigation: 5 areas + Settings. Every old page still exists; each one now lives as a tab inside an
 * area, so the sidebar stays short and the owner always knows where they are.
 */
export interface AreaTab {
  href: string;
  label: string;
  /** Other routes that should highlight this tab. */
  also?: string[];
  feature?: string;
  /** Hidden unless the plan includes the feature (instead of showing a lock). */
  hideIfLocked?: boolean;
}

export interface Area {
  key: string;
  label: string;
  href: string;
  icon: LucideIcon;
  badge?: "money" | "enquiries";
  tabs: AreaTab[];
  /** Extra routes that belong to this area without being a tab. */
  routes?: string[];
}

export const OWNER_AREAS: Area[] = [
  {
    key: "today", label: "Today", href: "/dashboard/overview", icon: Home,
    tabs: [], routes: ["/dashboard/overview", "/dashboard/actions", "/dashboard/assistant"],
  },
  {
    key: "members", label: "Members", href: "/dashboard/members", icon: Users,
    tabs: [
      { href: "/dashboard/members", label: "All members" },
      { href: "/dashboard/attendance", label: "Check-in" },
      { href: "/dashboard/memberships", label: "Plans & prices" },
    ],
    routes: ["/dashboard/member-portal"],
  },
  {
    key: "enquiries", label: "Enquiries", href: "/dashboard/leads", icon: Inbox, badge: "enquiries",
    tabs: [
      { href: "/dashboard/leads", label: "Inbox", feature: "lead_crm" },
      { href: "/dashboard/pipeline", label: "Board", feature: "lead_crm" },
      { href: "/dashboard/follow-ups", label: "Follow-ups", feature: "lead_crm" },
      { href: "/dashboard/trials", label: "Trials", feature: "trials" },
      { href: "/dashboard/sales-analytics", label: "Insights", also: ["/dashboard/lead-sources"], feature: "lead_crm" },
    ],
  },
  {
    key: "money", label: "Money", href: "/dashboard/money", icon: IndianRupee, badge: "money",
    tabs: [
      { href: "/dashboard/money", label: "Due now" },
      { href: "/dashboard/payments", label: "Payments" },
      { href: "/dashboard/recovery", label: "Renewal history", feature: "recovery_center" },
      { href: "/dashboard/revenue", label: "Reports", also: ["/dashboard/reports", "/dashboard/analytics"] },
    ],
  },
  {
    key: "grow", label: "Grow", href: "/dashboard/grow", icon: Sprout,
    tabs: [
      { href: "/dashboard/grow", label: "Overview" },
      { href: "/dashboard/local", label: "Google & reviews", feature: "local_seo" },
      { href: "/dashboard/seo", label: "Website health", feature: "seo_audit" },
      { href: "/dashboard/website-builder", label: "My website", also: ["/dashboard/seo/landing-pages"], feature: "website_builder" },
      { href: "/dashboard/sales-agent", label: "AI receptionist", feature: "ai_sales_agent" },
      { href: "/dashboard/ai-search", label: "ChatGPT & AI search", feature: "ai_search_readiness" },
    ],
  },
];

export const SETTINGS_AREA: Area = {
  key: "settings", label: "Settings", href: "/dashboard/settings", icon: Settings,
  tabs: [
    { href: "/dashboard/settings", label: "Gym profile" },
    { href: "/dashboard/gym-profile", label: "Info for AI replies" },
    { href: "/dashboard/trainers", label: "Team" },
    { href: "/dashboard/automation", label: "Reminders", feature: "automation" },
    { href: "/dashboard/integrations", label: "Connections" },
    { href: "/dashboard/ai-settings", label: "AI settings" },
    { href: "/dashboard/plan", label: "Subscription" },
    { href: "/dashboard/diet-plans", label: "Nutrition add-on", feature: "ai_diet", hideIfLocked: true },
  ],
  routes: ["/dashboard/workflows", "/dashboard/affiliate"],
};

export const TRAINER_AREAS: Area[] = [
  { key: "members", label: "My members", href: "/dashboard/members", icon: Users, tabs: [] },
  { key: "checkin", label: "Check-in", href: "/dashboard/attendance", icon: CalendarCheck, tabs: [] },
  { key: "trials", label: "Trials", href: "/dashboard/trials", icon: Sprout, tabs: [] },
  { key: "tasks", label: "My tasks", href: "/dashboard/follow-ups", icon: ClipboardList, tabs: [] },
];

const matches = (pathname: string, route: string) => pathname === route || pathname.startsWith(route + "/");

export function tabMatches(pathname: string, tab: AreaTab) {
  return [tab.href, ...(tab.also ?? [])].some((r) => matches(pathname, r));
}

export function areaFor(pathname: string, areas: Area[]): Area | undefined {
  // Longest match wins, so /dashboard/seo/landing-pages lands in Grow, not elsewhere.
  let best: { area: Area; len: number } | undefined;
  for (const area of areas) {
    const routes = [area.href, ...(area.routes ?? []), ...area.tabs.flatMap((t) => [t.href, ...(t.also ?? [])])];
    for (const r of routes) {
      if (matches(pathname, r) && (!best || r.length > best.len)) best = { area, len: r.length };
    }
  }
  return best?.area;
}
