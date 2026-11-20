"use client";

import { KeyRound, Plus, Search, Ticket, UserPlus, Users } from "lucide-react";
import { useState } from "react";
import { AssignMembershipForm } from "@/components/members/AssignMembershipForm";
import { MemberForm } from "@/components/members/MemberForm";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, Loading, Modal, PageHeader, Select } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { usePlans, useTrainers } from "@/hooks/useLookups";
import { useRole } from "@/hooks/useRole";
import { formatDate, humanize } from "@/lib/utils";
import { post } from "@/services/api";
import type { Member, Page } from "@/types";

const PAGE_SIZE = 25;

export default function MembersPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, loading, error, reload } = useApi<Page<Member>>("/members", { search, status, offset, limit: PAGE_SIZE });
  const { trainers, names: trainerNames } = useTrainers();
  const { plans } = usePlans();
  const [editing, setEditing] = useState<Member | "new" | null>(null);
  const [assignFor, setAssignFor] = useState<Member | null>(null);
  const [portalFor, setPortalFor] = useState<Member | null>(null);
  const isTrainer = useRole() === "trainer";

  return (
    <>
      <PageHeader
        title={isTrainer ? "My members" : "Members"}
        description="Everyone who trains at your gym."
        actions={!isTrainer && <Button onClick={() => setEditing("new")}><Plus className="h-4 w-4" /> Add member</Button>}
      />
      <Card>
        <div className="flex flex-col gap-2 border-b border-border p-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" />
            <Input className="pl-9" placeholder="Search name, phone or email" value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
          </div>
          <Select className="sm:w-44" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} placeholder="All statuses" options={["active", "expired", "inactive"]} />
        </div>
        {error && <div className="p-4"><ErrorNote message={error} /></div>}
        {loading && !data ? (
          <Loading />
        ) : !data?.items.length ? (
          <EmptyState icon={<Users className="h-8 w-8" />} title="No members found" description={search || status ? "Try a different search or filter." : "Add your first member to get started."} />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone</th>
                  <th>Status</th>
                  <th>Goal</th>
                  <th>Trainer</th>
                  <th>Joined</th>
                  {!isTrainer && <th className="text-right">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {data.items.map((m) => (
                  <tr key={m.id} className="hover:bg-surface-2/50">
                    <td>
                      <button className="font-medium hover:text-brand" onClick={() => !isTrainer && setEditing(m)}>{m.full_name}</button>
                      {m.email && <p className="text-xs text-muted">{m.email}</p>}
                    </td>
                    <td className="text-muted">{m.phone}</td>
                    <td><Badge value={m.status} /></td>
                    <td className="text-muted">{humanize(m.fitness_goal)}</td>
                    <td className="text-muted">{m.trainer_id ? trainerNames[m.trainer_id] : "—"}</td>
                    <td className="text-muted">{formatDate(m.joined_on)}</td>
                    {!isTrainer && (
                      <td className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="secondary" onClick={() => setAssignFor(m)}><Ticket className="h-3.5 w-3.5" /> Membership</Button>
                          {!m.user_id && (
                            <Button size="sm" variant="ghost" onClick={() => setPortalFor(m)} title="Give app access"><KeyRound className="h-3.5 w-3.5" /></Button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
