"use client";

import { CalendarCheck, IndianRupee, Inbox, UserPlus } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AppShell, type QuickAction } from "@/components/dashboard/AppShell";
import { OWNER_AREAS, SETTINGS_AREA, TRAINER_AREAS } from "@/components/dashboard/nav";
import { EntitlementsProvider, ToastProvider, useEntitlements } from "@/components/shared/growth";
import { Loading } from "@/components/shared/ui";
import { api, getRole } from "@/services/api";
import { getActingGymId } from "@/services/tenant";
import type { Gym, User } from "@/types";

const QUICK: QuickAction[] = [
  { href: "/dashboard/members?new=1", label: "Add member", icon: UserPlus },
  { href: "/dashboard/payments?new=1", label: "Take payment", icon: IndianRupee },
  { href: "/dashboard/attendance", label: "Check someone in", icon: CalendarCheck },
  { href: "/dashboard/leads?new=1", label: "Add enquiry", icon: Inbox },
];

function Shell({ role, children }: { role: string | null; children: React.ReactNode }) {
  const { ent } = useEntitlements();
  const pathname = usePathname();
  const [gym, setGym] = useState<Gym | null>(null);
  const [me, setMe] = useState<User | null>(null);
  const [badges, setBadges] = useState<{ money?: number; enquiries?: number }>({});
  const [acting, setActing] = useState<string | null>(null);
  const isTrainer = role === "trainer";
  const isStaff = role === "gym_owner" || role === "gym_manager" || (role === "platform_admin" && !!acting);

  useEffect(() => setActing(getActingGymId()), []);
  useEffect(() => {
    if (!role) return;
    api<User>("/auth/me").then(setMe).catch(() => setMe(null));
    if (role !== "platform_admin" || getActingGymId()) api<Gym>("/gym").then(setGym).catch(() => setGym(null));
  }, [role]);
  // Refresh the small nav counts whenever the owner moves between pages (they change as work gets done).
  useEffect(() => {
    if (isStaff) api<{ money: number; enquiries: number }>("/growth/badges").then(setBadges).catch(() => {});
  }, [isStaff, pathname]);

  const locked = (feature?: string) => Boolean(feature && ent && ent.features[feature] === false);
  const trialDaysLeft = ent?.status === "trialing" && ent.trial_ends_at
    ? Math.max(0, Math.ceil((new Date(ent.trial_ends_at).getTime() - Date.now()) / 86400000)) : null;

  const banner = role === "platform_admin" ? (
    <div className="border-b border-warning/30 bg-warning/10 px-4 py-2 text-center text-xs text-warning">
      {acting ? "You are viewing a gym as platform admin." : "Pick a gym to view from the admin console."}{" "}
      <Link href="/platform/admin/gyms" className="underline">Back to admin</Link>
    </div>
  ) : ent?.status === "trial_expired" ? (
    <div className="border-b border-danger/30 bg-danger/10 px-4 py-2 text-center text-sm text-danger">
      Your free trial has ended. Your data is safe. <Link href="/dashboard/plan" className="font-semibold underline">Choose a plan</Link> to switch reminders and growth tools back on.
    </div>
  ) : trialDaysLeft !== null && trialDaysLeft <= 5 && role === "gym_owner" ? (
    <div className="border-b border-brand/20 bg-brand/10 px-4 py-2 text-center text-sm">
      {trialDaysLeft === 0 ? "Your free trial ends today." : `${trialDaysLeft} day${trialDaysLeft === 1 ? "" : "s"} left in your free trial.`}{" "}
      <Link href="/dashboard/plan" className="font-semibold text-brand underline">Pick a plan</Link>
    </div>
  ) : null;

  return (
    <AppShell
      areas={isTrainer ? TRAINER_AREAS : OWNER_AREAS}
      footerArea={isTrainer ? undefined : SETTINGS_AREA}
      title={gym?.name ?? "GymFlow"}
      subtitle={isTrainer ? "Trainer" : ent?.plan_name ? `${ent.plan_name} plan` : undefined}
      userName={me?.full_name}
      badges={badges}
      isHidden={locked}
      quickActions={isStaff ? QUICK : undefined}
      banner={banner}
    >
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
