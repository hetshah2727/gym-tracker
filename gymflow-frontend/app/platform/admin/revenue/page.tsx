"use client";

import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ProductCard } from "@/components/affiliate/ProductCard";
import { Button, Card, ErrorNote, Field, Input, Loading, Modal, PageHeader, Textarea } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency } from "@/lib/utils";
import { post } from "@/services/api";
import type { AffiliateProduct } from "@/types";

export default function AdminRevenue() {
  const products = useApi<AffiliateProduct[]>("/affiliate/products");
  const [modal, setModal] = useState<"product" | "conversion" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <>
      <PageHeader
        title="Affiliate revenue"
        description="Manage the shared product catalogue and record eligible purchases from affiliate reports."
        actions={
          <>
            <Button variant="secondary" onClick={() => setModal("conversion")}>Record purchase</Button>
            <Button onClick={() => setModal("product")}><Plus className="h-4 w-4" /> Add product</Button>
          </>
        }
      />
      {notice && <p className="mb-4 rounded-lg border border-brand/30 bg-brand/10 px-3 py-2 text-sm text-brand">{notice}</p>}
      <Card title="Revenue share" className="mb-6 p-4">
        <p className="p-4 pt-0 text-sm text-muted">
          Each commission is split between the platform, the gym and the referring trainer (default 20% / 30% / 50%; configured on the API).
          If no trainer referred the sale, the trainer share goes to the gym.
        </p>
      </Card>
      {products.loading ? <Loading /> : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
          {products.data?.map((p) => <ProductCard key={p.id} product={p} badge={<span className="text-xs text-brand">{p.commission_rate_pct}%</span>} />)}
        </div>
      )}
      <Modal open={modal === "product"} onClose={() => setModal(null)} title="Add product">
        {modal === "product" && <ProductForm onSaved={() => { setModal(null); products.reload(); }} />}
      </Modal>
      <Modal open={modal === "conversion"} onClose={() => setModal(null)} title="Record eligible purchase">
        {modal === "conversion" && <ConversionForm onSaved={(msg) => { setModal(null); setNotice(msg); }} />}
      </Modal>
    </>
  );
}

function ProductForm({ onSaved }: { onSaved: () => void }) {
  const [form, setForm] = useState({ name: "", category: "supplements", price: "", external_url: "", asin: "", image_url: "", commission_rate_pct: "8", description: "" });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await post("/affiliate/products", {
        ...form,
        price: form.price ? Number(form.price) : null,
        commission_rate_pct: Number(form.commission_rate_pct),
        asin: form.asin || null,
        image_url: form.image_url || null,
      });
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
      <Field label="Name"><Input required value={form.name} onChange={set("name")} /></Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Category"><Input required value={form.category} onChange={set("category")} /></Field>
        <Field label="Price"><Input type="number" value={form.price} onChange={set("price")} /></Field>
        <Field label="Commission %"><Input type="number" step="0.1" value={form.commission_rate_pct} onChange={set("commission_rate_pct")} /></Field>
      </div>
      <Field label="Product URL"><Input type="url" required value={form.external_url} onChange={set("external_url")} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Amazon ASIN (optional)"><Input value={form.asin} onChange={set("asin")} /></Field>
        <Field label="Image URL"><Input value={form.image_url} onChange={set("image_url")} /></Field>
      </div>
      <Field label="Description"><Textarea value={form.description} onChange={set("description")} /></Field>
      <div className="flex justify-end"><Button type="submit" loading={saving}>Add product</Button></div>
    </form>
  );
}

function ConversionForm({ onSaved }: { onSaved: (msg: string) => void }) {
  const [form, setForm] = useState({ link_code: "", order_amount: "", commission_amount: "", external_order_id: "" });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const c = await post<{ commission_amount: number; platform_share: number; gym_share: number; trainer_share: number }>("/affiliate/conversions", {
        link_code: form.link_code.trim(),
        order_amount: Number(form.order_amount),
        commission_amount: form.commission_amount ? Number(form.commission_amount) : undefined,
        external_order_id: form.external_order_id || undefined,
      });
      onSaved(`Recorded ${formatCurrency(c.commission_amount)} commission: platform ${formatCurrency(c.platform_share)}, gym ${formatCurrency(c.gym_share)}, trainer ${formatCurrency(c.trainer_share)}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <ErrorNote message={error} />
      <Field label="Link code" hint="The ascsubtag / tracking code from the affiliate report"><Input required value={form.link_code} onChange={(e) => setForm({ ...form, link_code: e.target.value })} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Order amount"><Input type="number" required min={1} value={form.order_amount} onChange={(e) => setForm({ ...form, order_amount: e.target.value })} /></Field>
        <Field label="Commission" hint="Empty = order × product rate"><Input type="number" min={0} value={form.commission_amount} onChange={(e) => setForm({ ...form, commission_amount: e.target.value })} /></Field>
      </div>
      <Field label="External order id"><Input value={form.external_order_id} onChange={(e) => setForm({ ...form, external_order_id: e.target.value })} /></Field>
      <div className="flex justify-end"><Button type="submit" loading={saving}>Record</Button></div>
    </form>
  );
}
