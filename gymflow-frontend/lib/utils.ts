import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatCurrency(value: number | null | undefined, currency = "INR") {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}

export function formatDate(value: string | null | undefined, opts?: Intl.DateTimeFormatOptions) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-IN", opts ?? { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function humanize(value: string | null | undefined) {
  if (!value) return "—";
  return value.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function initials(name: string) {
  return name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

/** ₹3.2L / ₹1.1Cr style amounts for headline numbers (exact amounts stay in tables). */
export function formatCompact(value: number | null | undefined, currency = "INR") {
  if (value == null) return "—";
  if (currency === "INR" && Math.abs(value) >= 100000) {
    const crore = Math.abs(value) >= 10000000;
    const n = value / (crore ? 10000000 : 100000);
    return `₹${n.toFixed(n >= 10 ? 0 : 1).replace(/\.0$/, "")}${crore ? "Cr" : "L"}`;
  }
  return formatCurrency(value, currency);
}

/** WhatsApp "click to chat" link - works from any phone without the WhatsApp Business API. */
export function whatsappLink(phone: string | null | undefined, text?: string | null) {
  const digits = (phone ?? "").replace(/\D/g, "").replace(/^0+/, "");
  const intl = digits.length === 10 ? `91${digits}` : digits;
  return `https://wa.me/${intl}${text ? `?text=${encodeURIComponent(text)}` : ""}`;
}

export function firstName(name: string | null | undefined) {
  return (name ?? "").trim().split(/\s+/)[0] ?? "";
}

export function greeting(date = new Date()) {
  const h = date.getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/** "in 3 days" / "today" / "5 days late" for membership end dates and dues. */
export function daysPhrase(days: number | null | undefined, kind: "ends" | "due" = "ends") {
  if (days == null) return "—";
  if (days === 0) return kind === "ends" ? "ends today" : "due today";
  if (days > 0) return kind === "ends" ? `${days} day${days === 1 ? "" : "s"} left` : `due in ${days} day${days === 1 ? "" : "s"}`;
  const late = -days;
  return kind === "ends" ? `ended ${late} day${late === 1 ? "" : "s"} ago` : `${late} day${late === 1 ? "" : "s"} late`;
}
