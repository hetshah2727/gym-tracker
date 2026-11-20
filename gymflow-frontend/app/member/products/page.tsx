"use client";

import { ExternalLink, ShoppingBag, Star } from "lucide-react";
import { ProductCard } from "@/components/affiliate/ProductCard";
import { Card, EmptyState, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { API_URL } from "@/services/api";
import type { AffiliateProduct } from "@/types";

type MemberProduct = AffiliateProduct & { buy_url: string; recommended_by_trainer: boolean };

export default function MemberProducts() {
  const { data, loading } = useApi<MemberProduct[]>("/me/products");
  if (loading) return <Loading />;
  return (
    <>
      <PageHeader title="Recommended products" description="Supplements and gear picked by your gym and trainer." />
      {!data?.length ? (
        <Card><EmptyState icon={<ShoppingBag className="h-8 w-8" />} title="No recommendations yet" /></Card>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
          {data.map((p) => (
            <ProductCard
              key={p.id}
              product={p}
              badge={p.recommended_by_trainer ? <span className="inline-flex items-center gap-1 text-xs text-brand"><Star className="h-3 w-3" /> Trainer pick</span> : undefined}
              footer={
                <a href={new URL(p.buy_url, API_URL).toString()} target="_blank" rel="noopener sponsored"
                  className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-xs font-medium text-brand-fg">
                  Buy <ExternalLink className="h-3 w-3" />
                </a>
              }
            />
          ))}
        </div>
      )}
      <p className="mt-6 text-xs text-muted">Your gym may earn a small commission on purchases, at no extra cost to you.</p>
    </>
  );
}
