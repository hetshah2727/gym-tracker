"use client";

import { Copy, MessageCircle, Smartphone } from "lucide-react";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { formatCurrency, whatsappLink } from "@/lib/utils";
import { API_URL } from "@/services/api";

interface PayInfo { gym: string; phone: string | null; logo_url: string | null; upi_id: string; amount: number | null; upi_uri: string }

/** Public page a member opens from a WhatsApp reminder: scan the QR or open their UPI app. */
function PayPage() {
  const { slug } = useParams<{ slug: string }>();
  const params = useSearchParams();
  const amount = params.get("amount");
  const note = params.get("note");
  const [info, setInfo] = useState<PayInfo | null>(null);
  const [error, setError] = useState(false);
  const [copied, setCopied] = useState(false);
  const query = new URLSearchParams({ ...(amount ? { amount } : {}), ...(note ? { note } : {}) }).toString();

  useEffect(() => {
    fetch(`${API_URL}/public/sites/${slug}/pay?${query}`).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setInfo).catch(() => setError(true));
  }, [slug, query]);

  if (error) return <p className="p-8 text-center text-muted">This payment page isn&apos;t available. Please pay at the gym.</p>;
  if (!info) return <p className="p-8 text-center text-muted">Loading…</p>;
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col items-center justify-center gap-5 p-6 text-center">
      <div>
        <p className="text-sm text-muted">Pay</p>
        <h1 className="font-display text-2xl font-extrabold">{info.gym}</h1>
        {info.amount && <p className="num mt-2 font-display text-4xl font-extrabold">{formatCurrency(info.amount)}</p>}
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`${API_URL}/public/sites/${slug}/pay/qr.svg?${query}`} alt="UPI QR code" className="h-60 w-60 rounded-2xl border border-border bg-white p-3" />
      <p className="text-sm text-muted">Scan with Google Pay, PhonePe, Paytm or any UPI app</p>
      <a href={info.upi_uri} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-brand py-3 font-semibold text-brand-fg">
        <Smartphone className="h-5 w-5" /> Open my UPI app
      </a>
      <button onClick={() => { navigator.clipboard?.writeText(info.upi_id); setCopied(true); }}
        className="inline-flex items-center gap-2 text-sm text-muted underline"><Copy className="h-4 w-4" /> {copied ? "Copied" : `UPI ID: ${info.upi_id}`}</button>
      {info.phone && (
        <a href={whatsappLink(info.phone, `Hi, I've paid ${info.amount ? formatCurrency(info.amount) : "my fee"} by UPI.`)} target="_blank" rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-semibold">
          <MessageCircle className="h-4 w-4 text-money" /> Tell the gym I&apos;ve paid
        </a>
      )}
    </main>
  );
}

export default function Page() {
  return <Suspense><PayPage /></Suspense>;
}
