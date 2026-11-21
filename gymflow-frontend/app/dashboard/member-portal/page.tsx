"use client";

import Link from "next/link";
import { Note } from "@/components/shared/growth";
import { Card, EmptyState, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import type { Member, Page } from "@/types";

export default function MemberPortalPage() {
  const members = useApi<Page<Member>>("/members", { limit: 200 });
  const withAccess = (members.data?.items ?? []).filter((m) => m.user_id);
  return (
    <>
      <PageHeader title="Member portal" description="Members can log in to see their membership, payments, assigned diet plans and recommendations." />
      <Note className="mb-4">Give a member access from <Link href="/dashboard/members" className="underline">Members</Link> → open the member → Portal access. They log in at the normal login page.</Note>
      <Card title={`Members with portal access (${withAccess.length})`}>
        {members.loading ? <Loading /> : !withAccess.length ? <EmptyState title="No members have portal access yet" /> : (
          <ul className="divide-y divide-border/60">{withAccess.map((m) => <li key={m.id} className="px-4 py-2.5 text-sm">{m.full_name} <span className="text-xs text-muted">· {m.email}</span></li>)}</ul>
        )}
      </Card>
    </>
  );
}
