"use client";

import { CheckCircle2, CircleDashed } from "lucide-react";
import { Card, ErrorNote, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";

interface Integration { key: string; name: string; configured: boolean; detail: string | null }

export default function AdminIntegrations() {
  const { data, loading, error } = useApi<Integration[]>("/platform/integrations");
  return (
    <>
      <PageHeader title="Integrations" description="Third-party services are configured with environment variables on the API server." />
      {error && <ErrorNote message={error} />}
      {loading ? <Loading /> : (
        <Card>
          <ul className="divide-y divide-border/60">
            {data?.map((i) => (
              <li key={i.key} className="flex items-center justify-between gap-3 px-4 py-4">
                <div>
                  <p className="font-medium">{i.name}</p>
                  {i.detail && <p className="text-xs text-muted">{i.detail}</p>}
                </div>
                {i.configured ? (
                  <span className="flex items-center gap-1.5 text-sm text-brand"><CheckCircle2 className="h-4 w-4" /> Connected</span>
                ) : (
                  <span className="flex items-center gap-1.5 text-sm text-muted"><CircleDashed className="h-4 w-4" /> Not configured (dev mode)</span>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
      <p className="mt-4 text-xs text-muted">
        Unconfigured channels run in dev mode: messages and calls are logged on the server instead of being sent, so every flow can be tested end to end.
      </p>
    </>
  );
}
