"use client";

import { ExternalLink, Plus } from "lucide-react";
import { useState } from "react";
import { ConfirmDialog, FeatureGate, Note, SourceBadge, useAction } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, Field, Input, Loading, Modal, PageHeader, Select, Textarea } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDate } from "@/lib/utils";
import { del, get, patch, post } from "@/services/api";

interface LP { id: string; slug: string; service: string; area: string; seo_title: string; meta_description: string; h1: string; content: { intro?: string; sections?: { heading: string; body: string }[]; faqs?: { q: string; a: string }[]; cta?: string }; status: string; generated_by: string; warnings: string[]; published_at: string | null; public_url: string | null }

export default function LandingPagesPage() {
  const pages = useApi<LP[]>("/seo/landing-pages");
  const profile = useApi<{ area: string | null; service_areas: string[]; services: string[] }>("/gym-profile");
  const [create, setCreate] = useState({ service: "", area: "" });
  const [creating, setCreating] = useState(false);
  const [edit, setEdit] = useState<LP | null>(null);
  const [guide, setGuide] = useState<{ steps: string[]; note: string } | null>(null);
  const [remove, setRemove] = useState<LP | null>(null);
  const { busy, run } = useAction();
  const areas = Array.from(new Set([profile.data?.area, ...(profile.data?.service_areas ?? [])].filter(Boolean))) as string[];

  return (
    <FeatureGate feature="website_builder">
      <PageHeader title="Local landing pages" description="SEO pages for real services in the areas you actually serve, with an enquiry form that's attributed to the page."
        actions={<Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" /> New page</Button>} />
      <Note className="mb-4">Pages can only be created for your service areas (Gym Profile), up to 25 in total - hundreds of near-identical location pages hurt rankings. Each draft needs your review before publishing.</Note>
      <Card>
        {pages.loading ? <Loading /> : !pages.data?.length ? <EmptyState title="No landing pages" description="Create one, e.g. Personal Training in Gotri." /> : (
          <ul className="divide-y divide-border/60">{pages.data.map((p) => (
            <li key={p.id} className="flex flex-col gap-2 px-4 py-3 text-sm sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{p.h1} <Badge value={p.status} className="ml-1" /> <SourceBadge source={p.generated_by} /></p>
                <p className="truncate text-xs text-muted">{p.seo_title} · /{p.slug}{p.published_at && ` · published ${formatDate(p.published_at)}`}</p>
                {p.warnings.length > 0 && <p className="text-xs text-warning">Check: {p.warnings.join("; ")}</p>}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" onClick={() => setEdit(p)}>Edit</Button>
                {p.status === "published" ? <>
                  {p.public_url && <a href={p.public_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs text-brand hover:bg-surface-2"><ExternalLink className="h-3.5 w-3.5" /> View</a>}
                  <Button size="sm" variant="ghost" onClick={() => run("g" + p.id, () => get<{ steps: string[]; note: string }>(`/seo/landing-pages/${p.id}/indexing`)).then((g) => g && setGuide(g))}>Indexing</Button>
                  <Button size="sm" variant="ghost" onClick={() => run("u" + p.id, () => post(`/seo/landing-pages/${p.id}/unpublish`), "Unpublished").then(pages.reload)}>Unpublish</Button>
                </> : <Button size="sm" loading={busy === "p" + p.id} onClick={() => run("p" + p.id, () => post(`/seo/landing-pages/${p.id}/publish`), "Published").then(pages.reload)}>Publish</Button>}
                <Button size="sm" variant="ghost" onClick={() => setRemove(p)}>Delete</Button>
              </div>
            </li>))}</ul>
        )}
      </Card>
      <Modal open={creating} onClose={() => setCreating(false)} title="New landing page">
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); run("c", () => post<LP>("/seo/landing-pages", create), "Draft created - review before publishing").then((r) => { if (r) { setCreating(false); pages.reload(); setEdit({ ...r, public_url: null }); } }); }}>
          <Field label="Service"><Input required list="services" value={create.service} onChange={(e) => setCreate({ ...create, service: e.target.value })} placeholder="Personal Training" />
            <datalist id="services">{profile.data?.services.map((s) => <option key={s} value={s} />)}</datalist></Field>
          <Field label="Area" hint={areas.length ? undefined : "Add service areas in the Gym Profile first"}><Select required value={create.area} onChange={(e) => setCreate({ ...create, area: e.target.value })} placeholder="Choose an area" options={areas.map((a) => ({ value: a, label: a }))} /></Field>
          <div className="flex justify-end"><Button type="submit" loading={busy === "c"}>Create draft</Button></div>
        </form>
      </Modal>
      <Modal open={!!edit} onClose={() => setEdit(null)} title="Edit landing page" wide>
        {edit && (
          <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); run("s", () => patch(`/seo/landing-pages/${edit.id}`, { seo_title: edit.seo_title, meta_description: edit.meta_description, h1: edit.h1, content: edit.content }), "Saved").then(() => { setEdit(null); pages.reload(); }); }}>
            <Field label={`SEO title (${edit.seo_title.length}/60)`}><Input value={edit.seo_title} onChange={(e) => setEdit({ ...edit, seo_title: e.target.value })} /></Field>
            <Field label={`Meta description (${edit.meta_description.length}/160)`}><Textarea value={edit.meta_description} onChange={(e) => setEdit({ ...edit, meta_description: e.target.value })} /></Field>
            <Field label="H1"><Input value={edit.h1} onChange={(e) => setEdit({ ...edit, h1: e.target.value })} /></Field>
            <Field label="Intro"><Textarea value={edit.content.intro ?? ""} onChange={(e) => setEdit({ ...edit, content: { ...edit.content, intro: e.target.value } })} /></Field>
            {(edit.content.sections ?? []).map((s, i) => (
              <div key={i} className="grid gap-1 rounded-lg border border-border p-2">
                <Input value={s.heading} onChange={(e) => { const sections = [...(edit.content.sections ?? [])]; sections[i] = { ...s, heading: e.target.value }; setEdit({ ...edit, content: { ...edit.content, sections } }); }} />
                <Textarea value={s.body} onChange={(e) => { const sections = [...(edit.content.sections ?? [])]; sections[i] = { ...s, body: e.target.value }; setEdit({ ...edit, content: { ...edit.content, sections } }); }} />
              </div>
            ))}
            <div className="flex justify-end"><Button type="submit" loading={busy === "s"}>Save</Button></div>
          </form>
        )}
      </Modal>
      <Modal open={!!guide} onClose={() => setGuide(null)} title="Indexing guidance">
        {guide && <><ol className="list-decimal space-y-1.5 pl-5 text-sm">{guide.steps.map((s) => <li key={s}>{s}</li>)}</ol><p className="mt-3 text-xs text-muted">{guide.note}</p></>}
      </Modal>
      <ConfirmDialog open={!!remove} danger title="Delete landing page?" message={`"${remove?.h1}" will be removed from your site.`} confirmLabel="Delete"
        onClose={() => setRemove(null)} onConfirm={() => remove && run("del", () => del(`/seo/landing-pages/${remove.id}`), "Deleted").then(() => { setRemove(null); pages.reload(); })} />
    </FeatureGate>
  );
}
