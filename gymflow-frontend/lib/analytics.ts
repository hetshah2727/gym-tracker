"use client";

/**
 * Minimal, privacy-friendly product analytics: page views and a few funnel events (demo -> sign-up -> paid),
 * sent to PostHog's public capture API only when NEXT_PUBLIC_POSTHOG_KEY is set. No names, emails or phone
 * numbers are ever sent - just an anonymous random id kept in this browser.
 */
const KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const HOST = (process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://eu.i.posthog.com").replace(/\/$/, "");

function anonId(): string {
  try {
    let id = localStorage.getItem("gf-aid");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("gf-aid", id);
    }
    return id;
  } catch {
    return "anonymous";
  }
}

export function track(event: string, properties: Record<string, string | number | boolean | null> = {}) {
  if (!KEY || typeof window === "undefined") return;
  const body = JSON.stringify({
    api_key: KEY, event, distinct_id: anonId(),
    properties: { $current_url: window.location.origin + window.location.pathname, ...properties },
  });
  try {
    if (!navigator.sendBeacon?.(`${HOST}/capture/`, new Blob([body], { type: "application/json" }))) {
      fetch(`${HOST}/capture/`, { method: "POST", body, keepalive: true, headers: { "Content-Type": "application/json" } }).catch(() => {});
    }
  } catch { /* analytics must never break the app */ }
}
