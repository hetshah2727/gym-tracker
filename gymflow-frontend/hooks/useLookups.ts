"use client";

import { useMemo } from "react";
import type { Member, MembershipPlan, Page, Trainer } from "@/types";
import { useApi } from "./useApi";

/** id -> name maps used to label foreign keys in tables. */
export function useMemberNames(enabled = true) {
  const { data, reload } = useApi<Page<Member>>(enabled ? "/members" : null, { limit: 200 });
  const members = useMemo(() => data?.items ?? [], [data]);
  const names = useMemo(() => Object.fromEntries(members.map((m) => [m.id, m.full_name])), [members]);
  return { members, names, reload };
}

export function useTrainers() {
  const { data } = useApi<Trainer[]>("/trainers");
  const trainers = useMemo(() => data ?? [], [data]);
  const names = useMemo(() => Object.fromEntries(trainers.map((t) => [t.id, t.full_name])), [trainers]);
  return { trainers, names };
}

export function usePlans(includeInactive = false) {
  const { data, reload } = useApi<MembershipPlan[]>("/membership-plans", { include_inactive: includeInactive });
  const plans = useMemo(() => data ?? [], [data]);
  const names = useMemo(() => Object.fromEntries(plans.map((p) => [p.id, p.name])), [plans]);
  return { plans, names, reload };
}
