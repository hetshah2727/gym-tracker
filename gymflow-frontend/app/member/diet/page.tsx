"use client";

import { Utensils } from "lucide-react";
import { DietPlanView } from "@/components/diet/DietPlanView";
import { Card, EmptyState, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import type { DietPlan } from "@/types";

export default function MemberDiet() {
  const { data, loading } = useApi<DietPlan[]>("/me/diet-plans");
  if (loading) return <Loading />;
  const plan = data?.[0];
  return (
    <>
      <PageHeader title={plan?.title ?? "My diet plan"} description="Prepared and reviewed by your trainer." />
      {plan ? (
        <Card className="p-5"><DietPlanView plan={plan} showStatus={false} /></Card>
      ) : (
        <Card><EmptyState icon={<Utensils className="h-8 w-8" />} title="No diet plan yet" description="Ask your trainer to create one for you." /></Card>
      )}
    </>
  );
}
