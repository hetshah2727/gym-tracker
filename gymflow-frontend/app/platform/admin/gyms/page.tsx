"use client";

import { Building2, LogIn, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Button, Card, EmptyState, ErrorNote, Input, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDate } from "@/lib/utils";
import { patch } from "@/services/api";
import { setActingGymId } from "@/services/tenant";
import type { TenantSummary } from "@/types";

export default function AdminGyms() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const { data, loading, error, reload } = useApi<TenantSummary[]>("/platform/gyms", { search });
  const [busy, setBusy] = useState<string | null>(null);

  async function toggle(g: TenantSummary) {
    if (g.is_active && !confirm(`Suspend ${g.name}? Their staff and members won't be able to log in.`)) return;
    setBusy(g.id);
    await patch(`/platform/gyms/${g.id}`, { is_active: !g.is_active }).finally(() => setBusy(null));
    reload();
  }

  function openAs(g: TenantSummary) {
    setActingGymId(g.id);
    router.push("/dashboard/overview");
  }

  return (
    <>
      <PageHeader title="Gyms" description="Every tenant on the platform." />
      <Card>
        <div className="border-b border-border p-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" />
            <Input className="pl-9" placeholder="Search gyms" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>
        {error && <div className="p-4"><ErrorNote message={error} /></div>}
        {loading && !data ? <Loading /> : !data?.length ? <EmptyState icon={<Building2 className="h-8 w-8" />} title="No gyms" /> : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead><tr><th>Gym</th><th>City</th><th>Members</th><th>Plan</th><th>Subscription</th><th>Joined</th><th className="text-right">Actions</th></tr></thead>
              <tbody>
                {data.map((g) => (
                  <tr key={g.id} className={g.is_active ? "" : "opacity-60"}>
                    <td><p className="font-medium">{g.name}</p><p className="text-xs text-muted">{g.email}</p></td>
                    <td className="text-muted">{g.city ?? "—"}</td>
                    <td className="tabular-nums">{g.member_count}</td>
                    <td className="text-muted">{g.plan_name ?? "—"}</td>
                    <td>{g.is_active ? <Badge value={g.subscription_status} /> : <Badge value="cancelled" />}</td>
                    <td className="text-muted">{formatDate(g.created_at)}</td>
                    <td className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="secondary" onClick={() => openAs(g)}><LogIn className="h-3.5 w-3.5" /> Open</Button>
                        <Button size="sm" variant={g.is_active ? "ghost" : "primary"} loading={busy === g.id} onClick={() => toggle(g)}>
                          {g.is_active ? "Suspend" : "Reactivate"}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
