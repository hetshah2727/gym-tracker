"use client";

import { DndContext, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { Search } from "lucide-react";
import { useState } from "react";
import { LeadDrawer, heat, stageLabel, type LeadRow } from "@/components/growth/LeadDrawer";
import { ConfirmDialog, FeatureGate, useAction } from "@/components/shared/growth";
import { ErrorNote, Input, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { humanize } from "@/lib/utils";
import { post } from "@/services/api";

interface Column { status: string; total: number; leads: LeadRow[] }

function Card({ lead, onOpen }: { lead: LeadRow; onOpen: () => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: lead.id, data: { lead } });
  return (
    <div ref={setNodeRef} {...listeners} {...attributes} onClick={onOpen}
      style={transform ? { transform: `translate(${transform.x}px, ${transform.y}px)` } : undefined}
      className={`cursor-grab rounded-lg border border-border bg-surface p-2.5 text-xs shadow-sm ${isDragging ? "z-10 opacity-80" : ""}`}>
      <p className="truncate text-sm font-medium">{lead.name}</p>
      <p className="mt-0.5 text-muted">{humanize(lead.source)} · {heat(lead.score).label}</p>
      {!lead.first_response_at && lead.status === "new" && <p className="mt-1 text-warning">No response yet</p>}
    </div>
  );
}

function Lane({ col, children }: { col: Column; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: col.status });
  return (
    <div ref={setNodeRef} className={`flex w-64 shrink-0 flex-col rounded-xl border bg-surface-2/50 ${isOver ? "border-brand" : "border-border"}`}>
      <div className="flex items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
        <span>{stageLabel(col.status)}</span><span className="tabular-nums">{col.total}</span>
      </div>
      <div className="flex max-h-[65vh] flex-col gap-2 overflow-y-auto p-2">{children}</div>
    </div>
  );
}

export default function PipelinePage() {
  const [q, setQ] = useState("");
  const data = useApi<{ columns: Column[] }>("/crm/pipeline", { q });
  const [open, setOpen] = useState<string | null>(null);
  const [pending, setPending] = useState<{ lead: LeadRow; to: string } | null>(null);
  const [lostReason, setLostReason] = useState("");
  const { busy, run } = useAction();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  function onDragEnd(e: DragEndEvent) {
    const lead = e.active.data.current?.lead as LeadRow | undefined;
    const to = e.over?.id as string | undefined;
    if (!lead || !to || to === lead.status) return;
    if (to === "converted") { setOpen(lead.id); return; } // conversion needs plan + payment details
    setPending({ lead, to });
  }

  return (
    <FeatureGate feature="lead_crm">
      <PageHeader title="Sales pipeline" description="Drag a lead to move it. Joining opens the conversion form so the membership and payment are recorded."
        actions={<div className="relative"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" /><Input className="pl-9 sm:w-64" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search leads" /></div>} />
      {data.error && <ErrorNote message={data.error} />}
      {data.loading && !data.data ? <Loading /> : (
        <DndContext sensors={sensors} onDragEnd={onDragEnd}>
          <div className="flex gap-3 overflow-x-auto pb-4">
            {data.data?.columns.map((c) => (
              <Lane key={c.status} col={c}>
                {c.leads.map((l) => <Card key={l.id} lead={l} onOpen={() => setOpen(l.id)} />)}
                {c.total > c.leads.length && <p className="px-1 text-xs text-muted">+{c.total - c.leads.length} more in the inbox</p>}
              </Lane>
            ))}
          </div>
        </DndContext>
      )}
      <ConfirmDialog open={!!pending} title="Move lead?" busy={busy === "move"} confirmLabel="Move"
        message={pending && <>
          <p>Move <strong>{pending.lead.name}</strong> from {stageLabel(pending.lead.status)} to {stageLabel(pending.to)}?</p>
          {pending.to === "lost" && <Input className="mt-3" value={lostReason} onChange={(e) => setLostReason(e.target.value)} placeholder="Lost reason (required)" />}
        </>}
        onClose={() => { setPending(null); setLostReason(""); }}
        onConfirm={() => pending && (pending.to !== "lost" || lostReason) && run("move", () => post(`/crm/leads/${pending.lead.id}/status`, { status: pending.to, lost_reason: lostReason || undefined }), "Lead moved").then(() => { setPending(null); setLostReason(""); data.reload(); })} />
      <LeadDrawer leadId={open} onClose={() => setOpen(null)} onChanged={data.reload} />
    </FeatureGate>
  );
}
