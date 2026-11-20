"use client";

import { CalendarCheck, LogIn, LogOut, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge, Button, Card, EmptyState, ErrorNote, Input, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { useMemberNames } from "@/hooks/useLookups";
import { formatDateTime, todayISO } from "@/lib/utils";
import { post } from "@/services/api";
import type { Attendance } from "@/types";

export default function AttendancePage() {
  const [day, setDay] = useState(todayISO());
  const { data, loading, error, reload } = useApi<Attendance[]>("/attendance", { on: day });
  const { members, names } = useMemberNames();
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const matches = useMemo(() => {
    if (search.length < 2) return [];
    const q = search.toLowerCase();
    return members.filter((m) => m.full_name.toLowerCase().includes(q) || m.phone.includes(q)).slice(0, 6);
  }, [search, members]);

  async function checkIn(memberId: string) {
    setBusy(memberId);
    setMessage(null);
    try {
      await post("/attendance/check-in", { member_id: memberId });
      setSearch("");
      reload();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Check-in failed");
    } finally {
      setBusy(null);
    }
  }

  async function checkOut(id: string) {
    setBusy(id);
    await post(`/attendance/${id}/check-out`).finally(() => setBusy(null));
    reload();
  }

  return (
    <>
      <PageHeader title="Attendance" description="Check members in and see who trained today." />
      <Card className="mb-6 p-4">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" />
          <Input className="pl-9" placeholder="Type a member's name or phone to check in" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        {message && <div className="mt-3"><ErrorNote message={message} /></div>}
        {matches.length > 0 && (
          <ul className="mt-2 divide-y divide-border/60 rounded-lg border border-border">
            {matches.map((m) => (
              <li key={m.id} className="flex items-center justify-between px-3 py-2 text-sm">
                <span>
                  {m.full_name} <span className="text-muted">· {m.phone}</span> <Badge value={m.status} className="ml-1" />
                </span>
                <Button size="sm" loading={busy === m.id} onClick={() => checkIn(m.id)}><LogIn className="h-3.5 w-3.5" /> Check in</Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title={`Check-ins${data ? ` (${data.length})` : ""}`} actions={<Input type="date" className="w-auto py-1" value={day} onChange={(e) => setDay(e.target.value)} />}>
        {error && <div className="p-4"><ErrorNote message={error} /></div>}
        {loading && !data ? (
          <Loading />
        ) : !data?.length ? (
          <EmptyState icon={<CalendarCheck className="h-8 w-8" />} title="No check-ins" description="Nobody has checked in on this day yet." />
        ) : (
          <table className="table-base">
            <thead><tr><th>Member</th><th>In</th><th>Out</th><th className="text-right"></th></tr></thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td className="font-medium">{names[a.member_id] ?? "—"}</td>
                  <td className="text-muted">{formatDateTime(a.check_in_at)}</td>
                  <td className="text-muted">{formatDateTime(a.check_out_at)}</td>
                  <td className="text-right">
                    {!a.check_out_at && (
                      <Button size="sm" variant="ghost" loading={busy === a.id} onClick={() => checkOut(a.id)}><LogOut className="h-3.5 w-3.5" /> Check out</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
