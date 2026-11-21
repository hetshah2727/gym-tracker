import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { LandingPageView } from "@/components/website-editor/LandingPageView";
import type { PublicSite } from "@/types";

const API = process.env.API_URL_INTERNAL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function getPage(slug: string, page: string): Promise<PublicSite | null> {
  const res = await fetch(`${API}/public/sites/${encodeURIComponent(slug)}/pages/${encodeURIComponent(page)}`, { next: { revalidate: 60 } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load page (${res.status})`);
  return res.json();
}

type Params = { params: Promise<{ slug: string; page: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug, page } = await params;
  const data = await getPage(slug, page);
  if (!data?.page) return { title: "Page not found" };
  return { title: data.page.seo_title, description: data.page.meta_description, alternates: { canonical: `/sites/${slug}/${page}` } };
}

export default async function LandingPage({ params }: Params) {
  const { slug, page } = await params;
  const data = await getPage(slug, page);
  if (!data?.page) notFound();
  return <LandingPageView data={data} slug={slug} />;
}
