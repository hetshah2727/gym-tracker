"use client";

import { Plus, UserCog } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, Loading, Modal, PageHeader, Select, Textarea } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { humanize, initials } from "@/lib/utils";
import { patch, post } from "@/services/api";
import type { Trainer, User } from "@/types";

export default function TrainersPage() {
  const { data: trainers, loading, error, reload } = useApi<Trainer[]>("/trainers");
  const { data: staff, reload: reloadStaff } = useApi<User[]>("/users");
  const [modal, setModal] = useState<"trainer" | "staff" | Trainer | null>(null);

  return (
    <>
      <PageHeader
        title="Trainers & staff"
        description="Trainer profiles appear on your website; staff logins can use the dashboard."
        actions={
          <>
            <Button variant="secondary" onClick={() => setModal("staff")}>Add staff login</Button>
            <Button onClick={() => setModal("trainer")}><Plus className="h-4 w-4" /> Add trainer</Button>
          </>
        }
      />
      {error && <ErrorNote message={error} />}
      {loading && !trainers ? (
        <Loading />
      ) : !trainers?.length ? (
        <Card><EmptyState icon={<UserCog className="h-8 w-8" />} title="No trainers yet" description="Add trainers to assign members and share product recommendations." /></Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {trainers.map((t) => (
            <button key={t.id} onClick={() => setModal(t)} className={`card p-4 text-left transition hover:border-brand/50 ${t.is_active ? "" : "opacity-60"}`}>
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand/15 text-sm font-semibold text-brand">{initials(t.full_name)}</div>
                <div>
                  <p className="font-medium">{t.full_name}</p>
                  <p className="text-xs text-muted">{t.specialization ?? "Trainer"}{t.user_id ? " · has login" : ""}</p>
                </div>
              </div>
              {t.bio && <p className="mt-3 line-clamp-2 text-sm text-muted">{t.bio}</p>}
            </button>
          ))}
        </div>
      )}

      <Card title="Staff logins" className="mt-6">
        <table className="table-base">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th></tr></thead>
          <tbody>
            {staff?.map((u) => (
              <tr key={u.id}><td className="font-medium">{u.full_name}</td><td className="text-muted">{u.email}</td><td><Badge value={u.role} /></td></tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Modal open={modal !== null} onClose={() => setModal(null)} title={modal === "staff" ? "Add staff login" : modal === "trainer" ? "Add trainer" : "Edit trainer"}>
        {modal === "staff" && <StaffForm onSaved={() => { setModal(null); reload(); reloadStaff(); }} />}
        {modal !== null && modal !== "staff" && (
          <TrainerForm trainer={modal === "trainer" ? undefined : modal} onSaved={() => { setModal(null); reload(); }} />
        )}
      </Modal>
    </>
  );
}

function TrainerForm({ trainer, onSaved }: { trainer?: Trainer; onSaved: () => void }) {
  const [form, setForm] = useState({
    full_name: trainer?.full_name ?? "", phone: trainer?.phone ?? "", email: trainer?.email ?? "",
    specialization: trainer?.specialization ?? "", bio: trainer?.bio ?? "", photo_url: trainer?.photo_url ?? "",
  });
  const [active, setActive] = useState(trainer?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v || null]));
    try {
      if (trainer) await patch(`/trainers/${trainer.id}`, { ...body, is_active: active });
      else await post("/trainers", body);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <ErrorNote message={error} />
      <Field label="Full name"><Input required value={form.full_name} onChange={set("full_name")} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Phone"><Input value={form.phone} onChange={set("phone")} /></Field>
        <Field label="Email"><Input type="email" value={form.email} onChange={set("email")} /></Field>
      </div>
      <Field label="Specialization"><Input value={form.specialization} onChange={set("specialization")} placeholder="Strength & conditioning" /></Field>
      <Field label="Bio (shown on website)"><Textarea value={form.bio} onChange={set("bio")} /></Field>
      <Field label="Photo URL"><Input value={form.photo_url} onChange={set("photo_url")} /></Field>
      {trainer && (
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active</label>
      )}
      <div className="flex justify-end"><Button type="submit" loading={saving}>Save</Button></div>
    </form>
  );
}

function StaffForm({ onSaved }: { onSaved: () => void }) {
  const [form, setForm] = useState({ full_name: "", email: "", password: "", phone: "", role: "trainer" });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
          await post("/users", form);
          onSaved();
        } catch (err) {
          setError(err instanceof Error ? err.message : "Could not create login");
        } finally {
          setSaving(false);
        }
      }}
    >
      <ErrorNote message={error} />
      <Field label="Full name"><Input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
      <Field label="Role">
        <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
          options={["trainer", "gym_manager"].map((r) => ({ value: r, label: humanize(r) }))} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Email"><Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        <Field label="Phone"><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
      </div>
      <Field label="Temporary password" hint="At least 8 characters"><Input required minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
      <div className="flex justify-end"><Button type="submit" loading={saving}>Create login</Button></div>
    </form>
  );
}
