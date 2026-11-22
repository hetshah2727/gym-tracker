"use client";

import { FileSpreadsheet, KeyRound, MessageCircle, Plus, Search, Ticket, UserPlus, Users } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AssignMembershipForm } from "@/components/members/AssignMembershipForm";
import { ImportMembers } from "@/components/members/ImportMembers";
import { MemberForm } from "@/components/members/MemberForm";
import { MemberSheet } from "@/components/members/MemberSheet";
import { Button, Card, EmptyState, ErrorNote, Field, Input, Loading, Modal, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { usePlans, useTrainers } from "@/hooks/useLookups";
import { useRole } from "@/hooks/useRole";
import { cn, daysPhrase, formatCurrency, formatDate, initials, whatsappLink } from "@/lib/utils";
import { post } from "@/services/api";
import type { Member, Page } from "@/types";

const PAGE_SIZE = 25;

export default function MembersPage() {
  const params = useSearchParams();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [offset, setOffset] = useState(0);
  const { data, loading, error, reload } = useApi<Page<Member>>("/members", { search, status, offset, limit: PAGE_SIZE });
  const { trainers, names: trainerNames } = useTrainers();
  const { plans } = usePlans();
  const [editing, setEditing] = useState<Member | "new" | null>(null);
  const [assignFor, setAssignFor] = useState<Member | null>(null);
  const [portalFor, setPortalFor] = useState<Member | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const isTrainer = useRole() === "trainer";
  useEffect(() => { if (params.get("new") === "1") setEditing("new"); }, [params]);

  return (
    <>
      <PageHeader
        title={isTrainer ? "My members" : "Members"}
        description={data ? `${data.total} ${status ? status : ""} member${data.total === 1 ? "" : "s"}`.replace("  ", " ") : "Everyone who trains at your gym."}
        actions={!isTrainer && <>
          <Button variant="secondary" onClick={() => setImporting(true)}><FileSpreadsheet className="h-4 w-4" /> Import from Excel</Button>
          <Button onClick={() => setEditing("new")}><Plus className="h-4 w-4" /> Add member</Button>
        </>}
      />
      <Card>
        <div className="flex flex-col gap-2 border-b border-border p-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" />
            <Input className="pl-9" placeholder="Search name, phone or email" value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
          </div>
          <div className="scrollbar-none flex gap-1 overflow-x-auto" role="group" aria-label="Filter members">
            {[{ v: "", l: "All" }, { v: "active", l: "Active" }, { v: "expired", l: "Expired" }, { v: "inactive", l: "Inactive" }].map((f) => (
              <button key={f.v} onClick={() => { setStatus(f.v); setOffset(0); }}
                className={cn("whitespace-nowrap rounded-full border px-3.5 py-2 text-sm", status === f.v ? "border-fg bg-fg font-semibold text-bg" : "border-border text-muted hover:text-fg")}>{f.l}</button>
            ))}
          </div>
        </div>
        {error && <div className="p-4"><ErrorNote message={error} /></div>}
        {loading && !data ? (
          <Loading />
        ) : !data?.items.length ? (
          <EmptyState icon={<Users className="h-8 w-8" />} title="No members found" description={search || status ? "Try a different search or filter." : "Add your first member to get started."} />
        ) : (
          <ul className="divide-y divide-border/60">
            {data.items.map((m) => {
              const days = m.days_left;
              const tone = days == null ? "text-muted" : days < 0 ? "text-danger" : days <= 7 ? "text-warning" : "text-muted";
              return (
                <li key={m.id} className="flex flex-col gap-2 px-4 py-3 hover:bg-surface-2/60 sm:flex-row sm:items-center sm:gap-4 sm:px-5">
                  <button className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={() => !isTrainer && setViewing(m.id)}>
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-2 text-xs font-bold">{initials(m.full_name)}</span>
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">{m.full_name}</span>
                      <span className="block truncate text-xs text-muted">
                        {m.plan_name ?? "No plan yet"}
                        {days != null && <> · <span className={cn("font-medium", tone)}>{daysPhrase(days)}</span></>}
                        {m.trainer_id && trainerNames[m.trainer_id] && <> · {trainerNames[m.trainer_id]}</>}
                      </span>
                    </span>
                  </button>
                  <div className="flex items-center gap-2 pl-[3.25rem] text-xs sm:pl-0">
                    <span className="hidden w-28 text-muted md:block">{m.last_visit_at ? `Visited ${formatDate(m.last_visit_at, { day: "numeric", month: "short" })}` : "No visits yet"}</span>
                    <span className={cn("num w-24 font-semibold sm:text-right", m.due_amount ? "text-danger" : "text-muted")}>
                      {m.due_amount ? `${formatCurrency(m.due_amount)} due` : "Paid up"}
                    </span>
                    <span className="ml-auto flex gap-1 sm:ml-0">
                      <a href={whatsappLink(m.phone)} target="_blank" rel="noreferrer" className="rounded-xl border border-border p-2 hover:bg-surface-2" aria-label={`WhatsApp ${m.full_name}`}>
                        <MessageCircle className="h-4 w-4 text-money" />
                      </a>
                      {!isTrainer && <Button size="sm" variant="secondary" onClick={() => setAssignFor(m)}><Ticket className="h-3.5 w-3.5" /> {days != null ? "Renew" : "Add plan"}</Button>}
                      {!isTrainer && !m.user_id && (
                        <Button size="sm" variant="ghost" onClick={() => setPortalFor(m)} title="Give app access" aria-label="Give member app access"><KeyRound className="h-3.5 w-3.5" /></Button>
                      )}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {data && data.total > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t border-border px-4 py-3 text-xs text-muted">
            <span>{offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {data.total}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(offset - PAGE_SIZE)}>Previous</Button>
              <Button size="sm" variant="secondary" disabled={offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Add member" : "Edit member"} wide>
        {editing !== null && (
          <MemberForm
            member={editing === "new" ? undefined : editing}
            trainers={trainers}
            onSaved={(saved) => {
              setEditing(null);
              reload();
              if (editing === "new") setAssignFor(saved);
            }}
          />
        )}
      </Modal>

      <Modal open={!!assignFor} onClose={() => setAssignFor(null)} title={`Membership for ${assignFor?.full_name ?? ""}`}>
        {assignFor && (
          <AssignMembershipForm members={[assignFor]} plans={plans} defaultMemberId={assignFor.id} onSaved={() => { setAssignFor(null); reload(); }} />
        )}
      </Modal>

      <MemberSheet memberId={viewing} onClose={() => setViewing(null)}
        onEdit={(m) => { setViewing(null); setEditing(m); }} onRenew={(m) => { setViewing(null); setAssignFor(m); }} />

      <Modal open={importing} onClose={() => { setImporting(false); reload(); }} title="Import members from Excel" wide>
        {importing && <ImportMembers onDone={() => reload()} />}
      </Modal>

      <Modal open={!!portalFor} onClose={() => setPortalFor(null)} title="Member app access">
        {portalFor && <PortalAccessForm member={portalFor} onDone={() => { setPortalFor(null); reload(); }} />}
      </Modal>
    </>
  );
}

function PortalAccessForm({ member, onDone }: { member: Member; onDone: () => void }) {
  const [email, setEmail] = useState(member.email ?? "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setSaving(true);
        setError(null);
        try {
          await post(`/members/${member.id}/portal-access`, { email, password });
          onDone();
        } catch (err) {
          setError(err instanceof Error ? err.message : "Failed");
        } finally {
          setSaving(false);
        }
      }}
    >
      <p className="text-sm text-muted">{member.full_name} will be able to log in to see their membership, diet plan and recommended products.</p>
      <ErrorNote message={error} />
      <Field label="Login email"><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
      <Field label="Temporary password" hint="Share it with the member; at least 8 characters."><Input required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
      <div className="flex justify-end"><Button type="submit" loading={saving}><UserPlus className="h-4 w-4" /> Create login</Button></div>
    </form>
  );
}
