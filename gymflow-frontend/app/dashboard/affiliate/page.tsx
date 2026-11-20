"use client";

import { Check, Copy, IndianRupee, Link2, MousePointerClick, ShoppingCart } from "lucide-react";
import { useMemo, useState } from "react";
import { ProductCard } from "@/components/affiliate/ProductCard";
import { StatCard } from "@/components/dashboard/StatCard";
import { Button, Card, EmptyState, ErrorNote, Loading, PageHeader, Select, Tabs } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { useTrainers } from "@/hooks/useLookups";
import { useRole } from "@/hooks/useRole";
import { formatCurrency } from "@/lib/utils";
import { API_URL, post } from "@/services/api";
import type { AffiliateEarnings, AffiliateLink, AffiliateProduct } from "@/types";

type View = "catalogue" | "links";

function absoluteShareUrl(link: AffiliateLink) {
  // share_url is an API path ("/api/v1/affiliate/r/<code>"); make it absolute against the API origin.
  return new URL(link.share_url ?? "", API_URL).toString();
}

export default function AffiliatePage() {
  const role = useRole();
  const isTrainer = role === "trainer";
  const [view, setView] = useState<View>("catalogue");
  const [category, setCategory] = useState("");
  const products = useApi<AffiliateProduct[]>("/affiliate/products", { category });
  const links = useApi<AffiliateLink[]>("/affiliate/links");
  const earnings = useApi<AffiliateEarnings>("/affiliate/earnings");
  const { trainers } = useTrainers();
  const [trainerId, setTrainerId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const linkByProduct = useMemo(() => {
    const map: Record<string, AffiliateLink> = {};
    for (const l of links.data ?? []) if (isTrainer || (l.trainer_id ?? "") === trainerId) map[l.product_id] = l;
    return map;
  }, [links.data, trainerId, isTrainer]);
  const productNames = useMemo(() => Object.fromEntries((products.data ?? []).map((p) => [p.id, p.name])), [products.data]);
  const categories = useMemo(() => Array.from(new Set((products.data ?? []).map((p) => p.category))), [products.data]);

  async function createLink(productId: string) {
    setBusy(productId);
    try {
      await post<AffiliateLink>("/affiliate/links", { product_id: productId, trainer_id: trainerId || undefined });
      links.reload();
    } finally {
      setBusy(null);
    }
  }

  async function copy(link: AffiliateLink) {
    try {
      await navigator.clipboard.writeText(absoluteShareUrl(link));
      setCopied(link.id);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      /* clipboard unavailable */
    }
  }

  const e = earnings.data;
  return (
    <>
      <PageHeader title={isTrainer ? "Product recommendations" : "Affiliate store"} description="Recommend fitness products to members and earn a share of every eligible purchase." />
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label={isTrainer ? "Your earnings" : "Gym earnings"} value={formatCurrency(isTrainer ? e?.trainer_earnings : e?.gym_earnings)} icon={IndianRupee} tone="brand" />
        <StatCard label="Pending payout" value={formatCurrency(e?.pending_earnings)} icon={IndianRupee} tone="warning" />
        <StatCard label="Link clicks" value={e?.total_clicks ?? 0} icon={MousePointerClick} />
        <StatCard label="Purchases" value={e?.total_conversions ?? 0} hint={formatCurrency(e?.total_sales) + " in sales"} icon={ShoppingCart} />
      </div>

      <Tabs<View> value={view} onChange={setView} tabs={[{ value: "catalogue", label: "Catalogue" }, { value: "links", label: `Shared links (${links.data?.length ?? 0})` }]} />

      {view === "catalogue" ? (
        <>
          <div className="mb-4 flex flex-col gap-2 sm:flex-row">
            <Select className="sm:w-48" value={category} onChange={(ev) => setCategory(ev.target.value)} placeholder="All categories" options={categories} />
            {!isTrainer && (
              <Select className="sm:w-60" value={trainerId} onChange={(ev) => setTrainerId(ev.target.value)} placeholder="Links credited to: gym"
                options={trainers.map((t) => ({ value: t.id, label: `Credited to: ${t.full_name}` }))} />
            )}
          </div>
          {products.error && <ErrorNote message={products.error} />}
          {products.loading && !products.data ? (
            <Loading />
          ) : !products.data?.length ? (
            <Card><EmptyState title="No products yet" description="The platform team hasn't added products to the catalogue." /></Card>
          ) : (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
              {products.data.map((p) => {
                const link = linkByProduct[p.id];
                return (
                  <ProductCard
                    key={p.id}
                    product={p}
                    badge={<span className="text-xs text-brand">{p.commission_rate_pct}%</span>}
                    footer={
                      link ? (
                        <Button size="sm" variant="secondary" className="w-full" onClick={() => copy(link)}>
                          {copied === link.id ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />} {copied === link.id ? "Copied" : "Copy link"}
                        </Button>
                      ) : (
                        <Button size="sm" className="w-full" loading={busy === p.id} onClick={() => createLink(p.id)}>
                          <Link2 className="h-3.5 w-3.5" /> Get share link
                        </Button>
                      )
                    }
                  />
                );
              })}
            </div>
          )}
        </>
      ) : (
        <Card>
          {!links.data?.length ? (
            <EmptyState title="No links yet" description="Create a share link from the catalogue." />
          ) : (
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead><tr><th>Product</th><th>Credited to</th><th>Clicks</th><th className="text-right">Link</th></tr></thead>
                <tbody>
                  {links.data.map((l) => (
                    <tr key={l.id}>
                      <td className="font-medium">{productNames[l.product_id] ?? "—"}</td>
                      <td className="text-muted">{l.trainer_id ? trainers.find((t) => t.id === l.trainer_id)?.full_name ?? "Trainer" : "Gym"}</td>
                      <td className="tabular-nums">{l.clicks}</td>
                      <td className="text-right">
                        <Button size="sm" variant="secondary" onClick={() => copy(l)}>
                          {copied === l.id ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />} {copied === l.id ? "Copied" : "Copy"}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {!isTrainer && e && e.by_trainer.length > 0 && (
        <Card title="Trainer earnings" className="mt-6">
          <ul className="divide-y divide-border/60">
            {e.by_trainer.map((t) => (
              <li key={t.trainer_id} className="flex justify-between px-4 py-3 text-sm"><span>{t.name}</span><span className="tabular-nums">{formatCurrency(t.earnings)}</span></li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
