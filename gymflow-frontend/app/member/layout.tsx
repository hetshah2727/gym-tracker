"use client";

import { Home, ShoppingBag, Ticket, Utensils } from "lucide-react";
import { AppShell } from "@/components/dashboard/AppShell";

const AREAS = [
  { key: "home", href: "/member/dashboard", label: "Home", icon: Home, tabs: [] },
  { key: "membership", href: "/member/membership", label: "Membership", icon: Ticket, tabs: [] },
  { key: "diet", href: "/member/diet", label: "Diet", icon: Utensils, tabs: [] },
  { key: "products", href: "/member/products", label: "Products", icon: ShoppingBag, tabs: [] },
];

export default function MemberLayout({ children }: { children: React.ReactNode }) {
  return <AppShell title="My gym" areas={AREAS}>{children}</AppShell>;
}
