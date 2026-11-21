"use client";

import { Building2, CreditCard, IndianRupee, LayoutDashboard, Plug } from "lucide-react";
import { AppShell } from "@/components/dashboard/AppShell";

const AREAS = [
  { key: "dash", href: "/platform/admin/dashboard", label: "Dashboard", icon: LayoutDashboard, tabs: [] },
  { key: "gyms", href: "/platform/admin/gyms", label: "Gyms", icon: Building2, tabs: [] },
  { key: "subs", href: "/platform/admin/subscriptions", label: "Subscriptions", icon: CreditCard, tabs: [] },
  { key: "rev", href: "/platform/admin/revenue", label: "Affiliate", icon: IndianRupee, tabs: [] },
  { key: "int", href: "/platform/admin/integrations", label: "Integrations", icon: Plug, tabs: [] },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AppShell title="GymFlow" subtitle="Platform admin" areas={AREAS}>{children}</AppShell>;
}
