import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SiteRenderer } from "@/components/website-editor/BlockRenderer";
import { JsonLd } from "@/components/website-editor/PublicWidgets";
import type { PublicSite } from "@/types";

const API = process.env.API_URL_INTERNAL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function getSite(slug: string): Promise<PublicSite | null> {
  const res = await fetch(`${API}/public/sites/${encodeURIComponent(slug)}`, { next: { revalidate: 60 } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load site (${res.status})`);
  return res.json();
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const data = await getSite(slug);
  if (!data) return { title: "Site not found" };
  return { title: data.site.seo.title ?? data.gym.name, description: data.site.seo.description };
}

export default async function PublicGymSite({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const data = await getSite(slug);
  if (!data) notFound();
  return (
    <>
      <JsonLd data={data.site.seo.json_ld} />
      <SiteRenderer blocks={data.site.blocks} theme={data.site.theme} data={data} slug={data.site.slug} />
    </>
  );
}
