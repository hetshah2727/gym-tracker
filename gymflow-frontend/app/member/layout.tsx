"use client";

import { Home, ShoppingBag, Ticket, Utensils } from "lucide-react";
import { AppShell } from "@/components/dashboard/AppShell";

export default function MemberLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell
      subtitle="Member"
      sections={[
        {
          items: [
            { href: "/member/dashboard", label: "Home", icon: Home },
            { href: "/member/membership", label: "Membership", icon: Ticket },
            { href: "/member/diet", label: "Diet plan", icon: Utensils },
            { href: "/member/products", label: "Products", icon: ShoppingBag },
          ],
        },
      ]}
    >
      {children}
    </AppShell>
  );
}
