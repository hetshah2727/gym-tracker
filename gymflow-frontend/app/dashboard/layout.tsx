"use client";

import {
  BarChart3, CalendarCheck, CreditCard, Globe, LayoutDashboard, Settings, ShoppingBag,
  Ticket, UserCog, Users, Utensils, Workflow,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell, type NavSection } from "@/components/dashboard/AppShell";
import { getRole } from "@/services/api";
import { getActingGymId } from "@/services/tenant";

const OWNER_NAV: NavSection[] = [
  { items: [{ href: "/dashboard/overview", label: "Overview", icon: LayoutDashboard }] },
  {
    title: "Gym",
    items: [
      { href: "/dashboard/members", label: "Members", icon: Users },
      { href: "/dashboard/memberships", label: "Memberships", icon: Ticket },
      { href: "/dashboard/payments", label: "Payments", icon: CreditCard },
      { href: "/dashboard/attendance", label: "Attendance", icon: CalendarCheck },
      { href: "/dashboard/trainers", label: "Trainers & staff", icon: UserCog },
    ],
  },
  {
    title: "Grow",
    items: [
      { href: "/dashboard/automation", label: "Automation", icon: Workflow },
      { href: "/dashboard/diet-plans", label: "AI diet plans", icon: Utensils },
      { href: "/dashboard/affiliate", label: "Affiliate store", icon: ShoppingBag },
      { href: "/dashboard/website-builder", label: "Website builder", icon: Globe },
      { href: "/dashboard/analytics", label: "Reports", icon: BarChart3 },
    ],
  },
  { items: [{ href: "/dashboard/settings", label: "Settings", icon: Settings }] },
];

const TRAINER_NAV: NavSection[] = [
  {
    items: [
      { href: "/dashboard/members", label: "My members", icon: Users },
      { href: "/dashboard/attendance", label: "Attendance", icon: CalendarCheck },
      { href: "/dashboard/diet-plans", label: "Diet plans", icon: Utensils },
      { href: "/dashboard/affiliate", label: "Recommendations", icon: ShoppingBag },
    ],
  },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState<string | null>(null);
  const [acting, setActing] = useState<string | null>(null);
  useEffect(() => {
    setRole(getRole());
    setActing(getActingGymId());
  }, []);

  const banner =
    role === "platform_admin" ? (
      <div className="border-b border-warning/30 bg-warning/10 px-4 py-2 text-center text-xs text-warning">
        {acting ? "You are viewing a gym as platform admin." : "Pick a gym to view from the admin console."}{" "}
        <Link href="/platform/admin/gyms" className="underline">Back to admin</Link>
      </div>
    ) : undefined;

  return (
    <AppShell sections={role === "trainer" ? TRAINER_NAV : OWNER_NAV} subtitle={role === "trainer" ? "Trainer" : "Gym dashboard"} banner={banner}>
      {children}
    </AppShell>
  );
}
