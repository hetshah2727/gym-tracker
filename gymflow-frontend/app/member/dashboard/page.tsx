"use client";

import { AlertTriangle, Phone, Ticket, Utensils } from "lucide-react";
import Link from "next/link";
import { MacroBar } from "@/components/diet/DietPlanView";
import { Card, ErrorNote, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { DietPlan, Gym, Member, Membership, Payment } from "@/types";

export default function MemberHome() {
  const profile = useApi<Member>("/me/profile");
  const gym = useApi<Gym>("/me/gym");
  const memberships = useApi<Membership[]>("/me/memberships");
  const plans = useApi<DietPlan[]>("/me/diet-plans");
  const payments = useApi<Payment[]>("/me/payments");

  if (profile.loading) return <Loading />;
  if (profile.error) return <ErrorNote message={profile.error} />;

  const current = memberships.data?.find((m) => m.status === "active");
  const dues = payments.data?.filter((p) => p.status === "pending" || p.status === "overdue") ?? [];
  const diet = plans.data?.[0];

  return (
    <>
      <PageHeader title={`Hi, ${profile.data?.full_name.split(" ")[0]}`} description={gym.data ? `Welcome to ${gym.data.name}` : undefined} />

      {dues.length > 0 && (
        <div className="mb-4 flex items-start gap-3 rounded-xl border border-warning/40 bg-warning/10 p-4 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-warning" />
          <div>
            <p className="font-medium">You have {formatCurrency(dues.reduce((s, p) => s + Number(p.amount), 0))} due</p>
            <p className="text-muted">Please pay at the front desk{gym.data?.phone ? ` or call ${gym.data.phone}` : ""}.</p>
          </div>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="p-5">
          <div className="flex items-center gap-2 text-sm text-muted"><Ticket className="h-4 w-4" /> Membership</div>
          {current ? (
            <>
              <p className="mt-3 text-3xl font-semibold tabular-nums">{current.days_left}<span className="ml-1 text-base font-normal text-muted">days left</span></p>
              <p className="mt-1 text-sm text-muted">Valid until {formatDate(current.end_date)}</p>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface-2">
                <div
                  className={`h-full ${current.days_left! <= 7 ? "bg-warning" : "bg-brand"}`}
                  style={{
                    width: `${Math.max(4, Math.min(100, (current.days_left! / Math.max(1, (new Date(current.end_date).getTime() - new Date(current.start_date).getTime()) / 864e5)) * 100))}%`,
                  }}
                />
              </div>
            </>
          ) : (
            <p className="mt-3 text-sm text-muted">No active membership. Visit the front desk to renew.</p>
          )}
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2 text-sm text-muted"><Utensils className="h-4 w-4" /> Today&apos;s nutrition</div>
          {diet ? (
            <>
              <p className="mt-3 font-medium">{diet.title}</p>
              <div className="mt-3"><MacroBar macros={diet.macros} calories={diet.daily_calories} /></div>
              <Link href="/member/diet" className="mt-4 inline-block text-sm text-brand">See full plan →</Link>
            </>
          ) : (
            <p className="mt-3 text-sm text-muted">Your trainer hasn&apos;t shared a diet plan yet.</p>
          )}
        </Card>
      </div>

      {gym.data?.phone && (
        <a href={`tel:${gym.data.phone}`} className="mt-4 inline-flex items-center gap-2 text-sm text-muted hover:text-fg">
          <Phone className="h-4 w-4" /> Call {gym.data.name}
        </a>
      )}
    </>
  );
}
