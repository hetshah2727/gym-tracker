import { Package } from "lucide-react";
import type { ReactNode } from "react";
import { formatCurrency, humanize } from "@/lib/utils";
import type { AffiliateProduct } from "@/types";

export function ProductCard({ product, footer, badge }: { product: AffiliateProduct; footer?: ReactNode; badge?: ReactNode }) {
  return (
    <div className="card flex flex-col overflow-hidden">
      <div className="flex aspect-[4/3] items-center justify-center bg-surface-2">
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={product.image_url} alt={product.name} className="h-full w-full object-cover" />
        ) : (
          <Package className="h-10 w-10 text-muted" />
        )}
      </div>
      <div className="flex flex-1 flex-col p-4">
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="text-xs text-muted">{humanize(product.category)}</span>
          {badge}
        </div>
        <p className="font-medium leading-snug">{product.name}</p>
        <p className="mt-1 text-sm text-muted">{formatCurrency(product.price)}</p>
        {footer && <div className="mt-auto pt-3">{footer}</div>}
      </div>
    </div>
  );
}
