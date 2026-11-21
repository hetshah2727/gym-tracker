"use client";

import { ActionList, RecommendationList, type Action, type Recommendation } from "@/components/growth/Lists";
import { useAction } from "@/components/shared/growth";
import { Button, Card, ErrorNote, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { post } from "@/services/api";

export default function ActionsPage() {
  const actions = useApi<Action[]>("/growth/actions");
  const recs = useApi<Recommendation[]>("/growth/recommendations");
  const { busy, run } = useAction();
  const refresh = () => run("sync", () => post<Record<string, unknown>>("/growth/workflows/daily/run"),
    "Daily checks ran: renewals, dues, trials and leads are up to date").then(() => { actions.reload(); recs.reload(); });
  return (
    <>
      <PageHeader title="Today's actions" description="What to do today, worked out from your leads, trials, memberships, payments and audits."
        actions={<Button variant="secondary" loading={busy === "sync"} onClick={refresh}>Re-run daily checks</Button>} />
      {actions.error && <ErrorNote message={actions.error} />}
      <Card title="Actions">{actions.loading ? <Loading /> : <ActionList actions={actions.data ?? []} />}</Card>
      <Card title="Recommendations (with the data behind them)" className="mt-6">
        {recs.loading ? <Loading /> : <RecommendationList items={recs.data ?? []} />}
      </Card>
    </>
  );
}
