"use client";

import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ArrowLeft, Copy, ExternalLink, GripVertical, Monitor, Plus, Smartphone, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import { Badge, Button, ErrorNote, Field, Input, Loading, Select } from "@/components/shared/ui";
import { SiteRenderer, type SiteData } from "@/components/website-editor/BlockRenderer";
import { BlockSettings } from "@/components/website-editor/BlockSettings";
import { BLOCKS, newBlock } from "@/components/website-editor/blocks";
import { useApi } from "@/hooks/useApi";
import { cn } from "@/lib/utils";
import { post, put } from "@/services/api";
import type { BlockType, Gym, MembershipPlan, SiteBlock, Trainer, Website } from "@/types";

function SortableRow({ block, selected, onSelect, onDelete }: { block: SiteBlock; selected: boolean; onSelect: () => void; onDelete: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: block.id });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "flex items-center gap-2 rounded-lg border px-2 py-2 text-sm",
        selected ? "border-brand bg-brand/10" : "border-border bg-surface-2",
        isDragging && "z-10 opacity-80 shadow-lg",
      )}
    >
      <button {...attributes} {...listeners} className="cursor-grab touch-none text-muted hover:text-fg" aria-label="Drag to reorder">
        <GripVertical className="h-4 w-4" />
      </button>
      <button onClick={onSelect} className="flex-1 truncate text-left">{BLOCKS[block.type].label}</button>
      <button onClick={onDelete} className="text-muted hover:text-danger" aria-label="Remove block"><Trash2 className="h-3.5 w-3.5" /></button>
    </li>
  );
}

export default function EditorPage({ params }: { params: Promise<{ siteId: string }> }) {
  const { siteId } = use(params);
  const site = useApi<Website>(`/websites/${siteId}`);
  const gym = useApi<Gym>("/gym");
  const plans = useApi<MembershipPlan[]>("/membership-plans");
  const trainers = useApi<Trainer[]>("/trainers");

  const [blocks, setBlocks] = useState<SiteBlock[]>([]);
  const [theme, setTheme] = useState<Website["theme"]>({});
  const [meta, setMeta] = useState({ name: "", slug: "", custom_domain: "" });
  const [selected, setSelected] = useState<string | null>(null);
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [panel, setPanel] = useState<"blocks" | "design">("blocks");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState<"save" | "publish" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<{ published: boolean; at: string | null }>({ published: false, at: null });

  useEffect(() => {
    if (!site.data) return;
    setBlocks(site.data.blocks);
    setTheme(site.data.theme);
    setMeta({ name: site.data.name, slug: site.data.slug, custom_domain: site.data.custom_domain ?? "" });
    setStatus({ published: site.data.is_published, at: site.data.published_at });
  }, [site.data]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));

  const data: SiteData | null = useMemo(() => {
    if (!gym.data) return null;
    const g = gym.data;
    return {
      gym: { name: g.name, phone: g.phone, email: g.email, address: g.address, city: g.city, logo_url: g.logo_url, currency: g.currency },
      plans: (plans.data ?? []).map((p) => ({ id: p.id, name: p.name, duration_days: p.duration_days, price: Number(p.price), description: p.description })),
      trainers: (trainers.data ?? []).filter((t) => t.is_active).map((t) => ({ id: t.id, name: t.full_name, specialization: t.specialization, bio: t.bio, photo_url: t.photo_url })),
    };
  }, [gym.data, plans.data, trainers.data]);

  const edit = (next: SiteBlock[]) => { setBlocks(next); setDirty(true); };
  const selectedBlock = blocks.find((b) => b.id === selected);

  function onDragEnd(e: DragEndEvent) {
    if (!e.over || e.active.id === e.over.id) return;
    const from = blocks.findIndex((b) => b.id === e.active.id);
    const to = blocks.findIndex((b) => b.id === e.over!.id);
    edit(arrayMove(blocks, from, to));
  }

  async function save(publish: boolean) {
    setSaving(publish ? "publish" : "save");
    setError(null);
    try {
      await put<Website>(`/websites/${siteId}`, { blocks, theme, name: meta.name, slug: meta.slug, custom_domain: meta.custom_domain || null });
      if (publish) {
        const s = await post<Website>(`/websites/${siteId}/publish`);
        setStatus({ published: true, at: s.published_at });
      }
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setSaving(null);
    }
  }

  if (site.error) return <div className="p-6"><ErrorNote message={site.error} /></div>;
  if (!site.data || !data) return <Loading label="Opening editor…" />;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-border bg-surface px-3 py-2">
        <Link href="/dashboard/website-builder" className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-fg" aria-label="Back"><ArrowLeft className="h-4 w-4" /></Link>
        <div className="mr-auto min-w-0">
          <p className="truncate text-sm font-semibold">{meta.name}</p>
          <p className="flex items-center gap-2 text-xs text-muted">
            <Badge value={status.published ? "published" : "draft"} />
            {dirty ? "Unsaved changes" : "All changes saved"}
          </p>
        </div>
        <div className="hidden rounded-lg border border-border p-0.5 sm:flex">
          {(["desktop", "mobile"] as const).map((d) => (
            <button key={d} onClick={() => setDevice(d)} className={cn("rounded-md p-1.5", device === d ? "bg-surface-2 text-fg" : "text-muted")} aria-label={d}>
              {d === "desktop" ? <Monitor className="h-4 w-4" /> : <Smartphone className="h-4 w-4" />}
            </button>
          ))}
        </div>
        {status.published && (
          <a href={`/sites/${meta.slug}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-muted hover:text-fg">
            <ExternalLink className="h-3.5 w-3.5" /> View live
          </a>
        )}
        <Button variant="secondary" size="sm" onClick={() => save(false)} loading={saving === "save"} disabled={!dirty}>Save draft</Button>
        <Button size="sm" onClick={() => save(true)} loading={saving === "publish"}><Upload className="h-3.5 w-3.5" /> Publish</Button>
      </header>
      {error && <div className="p-2"><ErrorNote message={error} /></div>}

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <aside className="max-h-[45vh] w-full overflow-y-auto border-b border-border bg-surface p-3 md:max-h-none md:w-72 md:border-b-0 md:border-r">
          <div className="mb-3 flex gap-1 rounded-lg border border-border p-0.5 text-sm">
            {(["blocks", "design"] as const).map((p) => (
              <button key={p} onClick={() => setPanel(p)} className={cn("flex-1 rounded-md py-1 capitalize", panel === p ? "bg-surface-2 font-medium" : "text-muted")}>{p}</button>
            ))}
          </div>
          {panel === "blocks" ? (
            <>
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                <SortableContext items={blocks.map((b) => b.id)} strategy={verticalListSortingStrategy}>
                  <ul className="space-y-1.5">
                    {blocks.map((b) => (
                      <SortableRow key={b.id} block={b} selected={b.id === selected} onSelect={() => setSelected(b.id)}
                        onDelete={() => { edit(blocks.filter((x) => x.id !== b.id)); if (selected === b.id) setSelected(null); }} />
                    ))}
                  </ul>
                </SortableContext>
              </DndContext>
              <p className="mb-2 mt-5 text-xs font-medium uppercase tracking-wider text-muted">Add a section</p>
              <div className="grid grid-cols-2 gap-1.5">
                {(Object.keys(BLOCKS) as BlockType[]).map((type) => (
                  <button key={type} onClick={() => { const b = newBlock(type); edit([...blocks, b]); setSelected(b.id); }}
                    className="flex items-center gap-1.5 rounded-lg border border-dashed border-border px-2 py-2 text-left text-xs text-muted hover:border-brand hover:text-fg">
                    <Plus className="h-3 w-3 flex-shrink-0" /> {BLOCKS[type].label}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div className="space-y-4">
              <Field label="Site name"><Input value={meta.name} onChange={(e) => { setMeta({ ...meta, name: e.target.value }); setDirty(true); }} /></Field>
              <Field label="Site address" hint={`/sites/${meta.slug}`}><Input value={meta.slug} onChange={(e) => { setMeta({ ...meta, slug: e.target.value }); setDirty(true); }} /></Field>
              <Field label="Custom domain" hint="Point a CNAME to sites.gymflow.app, then enter it here.">
                <Input value={meta.custom_domain} placeholder="www.mygym.com" onChange={(e) => { setMeta({ ...meta, custom_domain: e.target.value }); setDirty(true); }} />
              </Field>
              <Field label="Brand colour">
                <div className="flex gap-2">
                  <input type="color" value={theme.primaryColor ?? "#16a34a"} onChange={(e) => { setTheme({ ...theme, primaryColor: e.target.value }); setDirty(true); }} className="h-9 w-12 cursor-pointer rounded border border-border bg-transparent" />
                  <Input value={theme.primaryColor ?? ""} onChange={(e) => { setTheme({ ...theme, primaryColor: e.target.value }); setDirty(true); }} />
                </div>
              </Field>
              <Field label="Mode"><Select value={theme.mode ?? "light"} onChange={(e) => { setTheme({ ...theme, mode: e.target.value as "light" | "dark" }); setDirty(true); }} options={["light", "dark"]} /></Field>
              <Field label="Font"><Select value={theme.font ?? "Inter"} onChange={(e) => { setTheme({ ...theme, font: e.target.value }); setDirty(true); }} options={["Inter", "Oswald", "Poppins", "Georgia"].map((f) => ({ value: f, label: f }))} /></Field>
              <Button variant="secondary" size="sm" className="w-full" onClick={() => navigator.clipboard?.writeText(`${window.location.origin}/sites/${meta.slug}`)}>
                <Copy className="h-3.5 w-3.5" /> Copy site link
              </Button>
            </div>
          )}
        </aside>

        <main className="min-h-0 flex-1 overflow-y-auto bg-bg p-3 sm:p-6">
          <div className={cn("mx-auto overflow-hidden rounded-xl border border-border shadow-2xl transition-all", device === "mobile" ? "max-w-[390px]" : "max-w-5xl")}>
            <SiteRenderer blocks={blocks} theme={theme} data={data} preview />
          </div>
        </main>

        {selectedBlock && (
          <aside className="max-h-[50vh] w-full overflow-y-auto border-t border-border bg-surface p-4 md:max-h-none md:w-80 md:border-l md:border-t-0">
            <BlockSettings block={selectedBlock} onChange={(props) => edit(blocks.map((b) => (b.id === selectedBlock.id ? { ...b, props } : b)))} />
            <Button variant="ghost" size="sm" className="mt-4" onClick={() => setSelected(null)}>Done</Button>
          </aside>
        )}
      </div>
    </div>
  );
}
