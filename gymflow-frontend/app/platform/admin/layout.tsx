"use client";

import { Building2, CreditCard, IndianRupee, LayoutDashboard, Plug } from "lucide-react";
import { AppShell } from "@/components/dashboard/AppShell";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell
      subtitle="Platform admin"
      sections={[
        {
          items: [
            { href: "/platform/admin/dashboard", label: "Dashboard", icon: LayoutDashboard },
            { href: "/platform/admin/gyms", label: "Gyms", icon: Building2 },
            { href: "/platform/admin/subscriptions", label: "Subscriptions", icon: CreditCard },
            { href: "/platform/admin/revenue", label: "Affiliate revenue", icon: IndianRupee },
            { href: "/platform/admin/integrations", label: "Integrations", icon: Plug },
          ],
        },
      ]}
    >
      {children}
    </AppShell>
  );
}
