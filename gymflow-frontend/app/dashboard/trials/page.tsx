"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { HBars } from "@/components/charts/Charts";
import { LeadDrawer } from "@/components/growth/LeadDrawer";
import { ConfirmDialog, FeatureGate, Kpi, Note, percent, useAction, useQueryTab } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, Field, Input, Loading, Modal, PageHeader, Select, Tabs } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { cn, formatDateTime, humanize } from "@/lib/utils";
import { post } from "@/services/api";

interface Trial { id: string; lead_id: string; lead_name: string | null; lead_phone: string | null; lead_status: string | null; trainer_name: string | null; starts_at: string; ends_at: string; status: string; source: string; reschedule_count: number; converted_membership_id: string | null }
interface Stats { total: number; upcoming: number; completed: number; no_shows: number; cancellations: number; pending_attendance_review: number; attendance_rate: number | null; trial_to_membership: number | null; converted: number; by_source: Record<string, number>; lost_reasons: Record<string, number> }
type Tab = "calendar" | "bookings" | "no-shows" | "conversion";
type View = "day" | "week" | "month";

const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const STATUS_TONE: Record<string, string> = { booked: "bg-sky-500/15 text-sky-300 border-sky-500/30", attended: "bg-brand/15 text-brand border-brand/30", no_show: "bg-danger/15 text-danger border-danger/30", pending_review: "bg-warning/15 text-warning border-warning/30", cancelled: "bg-surface-2 text-muted line-through border-border" };

function TrialChip({ t, onClick }: { t: Trial; onClick: () => void }) {
  return (
    <button onClick={onClick} className={cn("w-full truncate rounded-md border px-1.5 py-1 text-left text-[11px]", STATUS_TONE[t.status])}>
      {new Date(t.starts_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })} {t.lead_name}
    </button>
  );
}

export default function TrialsPage() {
  const [tab, setTab] = useQueryTab<Tab>("calendar");
  const [view, setView] = useState<View>("week");
  const [anchor, setAnchor] = useState(() => new Date());
  const range = view === "day" ? [anchor, anchor] : view === "week" ? [addDays(anchor, -((anchor.getDay() + 6) % 7)), addDays(anchor, 6 - ((anchor.getDay() + 6) % 7))]
    : [new Date(anchor.getFullYear(), anchor.getMonth(), 1), new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0)];
  const listRange = tab === "calendar" ? { start: iso(range[0]), end: iso(range[1]) } : { start: iso(addDays(new Date(), -45)), end: iso(addDays(new Date(), 30)) };
  const trials = useApi<Trial[]>("/trials", { ...listRange, status: tab === "no-shows" ? "" : undefined });
  const stats = useApi<Stats>(tab === "conversion" ? "/trials/analytics" : null, { days: 60 });
  const [selected, setSelected] = useState<Trial | null>(null);
  const [lead, setLead] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{ t: Trial; action: "no-show" | "cancel" } | null>(null);
  const [resched, setResched] = useState<Trial | null>(null);
  const [newSlot, setNewSlot] = useState("");
  const slots = useApi<{ starts_at: string; remaining: number }[]>(resched ? "/trials/slots" : null, { days: 10 });
  const { busy, run } = useAction();
  const reload = () => { trials.reload(); setSelected(null); };
  const act = (t: Trial, action: string, label: string) => run(action + t.id, () => post(`/trials/${t.id}/${action}`, action === "cancel" ? { reason: "Cancelled by staff" } : undefined), label).then(reload);

  const days: Date[] = [];
  for (let d = new Date(range[0]); d <= range[1]; d = addDays(d, 1)) days.push(new Date(d));
  const byDay = (d: Date) => (trials.data ?? []).filter((t) => iso(new Date(t.starts_at)) === iso(d));
  const now = Date.now();
  const review = (trials.data ?? []).filter((t) => t.status === "pending_review" || (t.status === "booked" && new Date(t.ends_at).getTime() < now));
  const noShows = (trials.data ?? []).filter((t) => t.status === "no_show");

  return (
    <FeatureGate feature="trials">
      <PageHeader title="Trials" description="Book, track and convert trial visits. Slots respect your trial hours, capacity and trainer availability." />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ value: "calendar", label: "Calendar" }, { value: "bookings", label: "Bookings" }, { value: "no-shows", label: "No-shows & attendance" }, { value: "conversion", label: "Conversion" }]} />

      {tab === "calendar" && (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
            <div className="flex items-center gap-1">
              <Button size="sm" variant="ghost" aria-label="Previous" onClick={() => setAnchor(view === "month" ? new Date(anchor.getFullYear(), anchor.getMonth() - 1, 1) : addDays(anchor, view === "day" ? -1 : -7))}><ChevronLeft className="h-4 w-4" /></Button>
              <Button size="sm" variant="secondary" onClick={() => setAnchor(new Date())}>Today</Button>
              <Button size="sm" variant="ghost" aria-label="Next" onClick={() => setAnchor(view === "month" ? new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1) : addDays(anchor, view === "day" ? 1 : 7))}><ChevronRight className="h-4 w-4" /></Button>
              <span className="ml-2 text-sm font-medium">{view === "month" ? anchor.toLocaleDateString("en-IN", { month: "long", year: "numeric" }) : `${range[0].toLocaleDateString("en-IN", { day: "numeric", month: "short" })}${view === "week" ? ` – ${range[1].toLocaleDateString("en-IN", { day: "numeric", month: "short" })}` : ""}`}</span>
            </div>
            <Tabs<View> value={view} onChange={setView} tabs={[{ value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" }]} />
          </div>
          {trials.loading ? <Loading /> : view === "day" ? (
            <ul className="divide-y divide-border/60">{byDay(anchor).length ? byDay(anchor).map((t) => (
              <li key={t.id} className="flex items-center justify-between px-4 py-3 text-sm"><button className="text-left" onClick={() => setSelected(t)}><p className="font-medium">{formatDateTime(t.starts_at)} · {t.lead_name}</p><p className="text-xs text-muted">{t.trainer_name ?? "Any trainer"} · {t.source}</p></button><Badge value={t.status} /></li>
            )) : <EmptyState title="No trials this day" />}</ul>
          ) : (
            <div className={cn("grid gap-px bg-border", view === "week" ? "grid-cols-7" : "grid-cols-7")}>
              {view === "month" && Array.from({ length: (range[0].getDay() + 6) % 7 }).map((_, i) => <div key={`pad${i}`} className="bg-surface" />)}
              {days.map((d) => (
                <div key={iso(d)} className={cn("min-h-[110px] bg-surface p-1.5", iso(d) === iso(new Date()) && "bg-brand/5")}>
                  <p className="mb-1 text-[11px] text-muted">{d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric" })}</p>
                  <div className="space-y-1">{byDay(d).slice(0, view === "month" ? 3 : 12).map((t) => <TrialChip key={t.id} t={t} onClick={() => setSelected(t)} />)}
                    {view === "month" && byDay(d).length > 3 && <p className="text-[10px] text-muted">+{byDay(d).length - 3} more</p>}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {(tab === "bookings" || tab === "no-shows") && (
        <Card title={tab === "bookings" ? "Trial bookings (last 45 days and next 30)" : "Needs attendance review"}>
          {tab === "no-shows" && <div className="p-4 pb-0"><Note>Past trials without recorded attendance are never assumed to be no-shows. Mark each one attended, or confirm the no-show to start a follow-up.</Note></div>}
          {trials.loading ? <Loading /> : (
            <TrialTable rows={tab === "bookings" ? trials.data ?? [] : review} onOpen={setSelected} />
          )}
          {tab === "no-shows" && <div className="border-t border-border"><p className="px-4 pt-3 text-sm font-medium">Confirmed no-shows</p><TrialTable rows={noShows} onOpen={setSelected} /></div>}
        </Card>
      )}

      {tab === "conversion" && (stats.loading || !stats.data ? <Loading /> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Total trials (60 days)" value={stats.data.total} />
            <Kpi label="Upcoming" value={stats.data.upcoming} />
            <Kpi label="Attendance rate" value={percent(stats.data.attendance_rate)} hint={`${stats.data.completed} attended · ${stats.data.no_shows} no-shows`} />
            <Kpi label="Trial → member" value={percent(stats.data.trial_to_membership)} hint={`${stats.data.converted} joined`} tone="brand" />
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Trials by lead source"><div className="p-4">{Object.keys(stats.data.by_source).length ? <HBars data={Object.entries(stats.data.by_source).map(([k, v]) => ({ label: humanize(k), value: v }))} valueLabel="Trials" /> : <EmptyState title="No trials yet" />}</div></Card>
            <Card title="Why trial leads were lost"><div className="p-4">{Object.keys(stats.data.lost_reasons).length ? <HBars data={Object.entries(stats.data.lost_reasons).map(([k, v]) => ({ label: k, value: v }))} valueLabel="Leads" /> : <EmptyState title="No lost trial leads" />}</div></Card>
          </div>
        </>
      ))}

      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected ? `Trial: ${selected.lead_name}` : "Trial"}>
        {selected && (
          <div className="space-y-3 text-sm">
            <p>{formatDateTime(selected.starts_at)} · {selected.trainer_name ?? "Any trainer"} · booked via {selected.source}</p>
            <p className="flex items-center gap-2"><Badge value={selected.status} /> {selected.lead_phone && <a className="text-brand" href={`tel:${selected.lead_phone}`}>{selected.lead_phone}</a>}</p>
            <div className="flex flex-wrap gap-2">
              {["booked", "pending_review", "no_show"].includes(selected.status) && new Date(selected.starts_at).getTime() < now &&
                <Button size="sm" loading={busy === "attended" + selected.id} onClick={() => act(selected, "attended", "Marked attended")}>Mark attended</Button>}
              {["booked", "pending_review"].includes(selected.status) && new Date(selected.starts_at).getTime() < now &&
                <Button size="sm" variant="danger" onClick={() => setConfirm({ t: selected, action: "no-show" })}>Confirm no-show</Button>}
              {["booked", "pending_review"].includes(selected.status) && <Button size="sm" variant="secondary" onClick={() => { setResched(selected); setSelected(null); }}>Reschedule</Button>}
              {["booked", "pending_review"].includes(selected.status) && <Button size="sm" variant="ghost" onClick={() => setConfirm({ t: selected, action: "cancel" })}>Cancel</Button>}
              <Button size="sm" variant="ghost" onClick={() => { setLead(selected.lead_id); setSelected(null); }}>Open lead</Button>
            </div>
          </div>
        )}
      </Modal>
      <Modal open={!!resched} onClose={() => setResched(null)} title="Reschedule trial">
        <Field label="New slot"><Select value={newSlot} onChange={(e) => setNewSlot(e.target.value)} placeholder="Choose a slot" options={(slots.data ?? []).map((s) => ({ value: s.starts_at, label: `${formatDateTime(s.starts_at)} · ${s.remaining} left` }))} /></Field>
        <div className="mt-4 flex justify-end"><Button disabled={!newSlot} loading={busy === "res"} onClick={() => resched && run("res", () => post(`/trials/${resched.id}/reschedule`, { starts_at: newSlot }), "Trial rescheduled").then((r) => { if (r) { setResched(null); setNewSlot(""); trials.reload(); } })}>Save</Button></div>
      </Modal>
      <ConfirmDialog open={!!confirm} danger title={confirm?.action === "cancel" ? "Cancel trial?" : "Confirm no-show?"} busy={!!busy}
        message={confirm?.action === "cancel" ? "The slot is released and open tasks are closed." : "This creates a recovery opportunity and a follow-up task with a drafted message."}
        onClose={() => setConfirm(null)} onConfirm={() => confirm && act(confirm.t, confirm.action, confirm.action === "cancel" ? "Trial cancelled" : "No-show confirmed").then(() => setConfirm(null))} />
      <LeadDrawer leadId={lead} onClose={() => setLead(null)} onChanged={trials.reload} />
    </FeatureGate>
  );
}

function TrialTable({ rows, onOpen }: { rows: Trial[]; onOpen: (t: Trial) => void }) {
  if (!rows.length) return <EmptyState title="Nothing here" />;
  return (
    <div className="overflow-x-auto"><table className="table-base">
      <thead><tr><th>When</th><th>Lead</th><th>Trainer</th><th>Source</th><th>Status</th></tr></thead>
      <tbody>{rows.map((t) => <tr key={t.id} className="cursor-pointer hover:bg-surface-2" onClick={() => onOpen(t)}><td>{formatDateTime(t.starts_at)}</td><td>{t.lead_name}<span className="block text-xs text-muted">{t.lead_phone}</span></td><td className="text-xs">{t.trainer_name ?? "Any"}</td><td className="text-xs">{t.source}</td><td><Badge value={t.status} />{t.converted_membership_id && <span className="ml-1 text-xs text-brand">joined</span>}</td></tr>)}</tbody>
    </table></div>
  );
}
