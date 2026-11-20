import { getActingGymId } from "./tenant";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
export const TOKEN_COOKIE = "gf_token";
export const ROLE_COOKIE = "gf_role";

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function getToken() {
  return readCookie(TOKEN_COOKIE);
}

export function getRole() {
  return readCookie(ROLE_COOKIE);
}

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) {
      const loc = Array.isArray(detail[0].loc) ? detail[0].loc.slice(-1)[0] : "";
      return loc ? `${loc}: ${detail[0].msg}` : detail[0].msg;
    }
  }
  return fallback;
}

type Query = Record<string, string | number | boolean | null | undefined>;

export function withQuery(path: string, query?: Query) {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export async function api<T>(path: string, init: RequestInit & { query?: Query } = {}): Promise<T> {
  const { query, headers, ...rest } = init;
  const token = getToken();
  const actingGym = getActingGymId();
  const res = await fetch(`${API_URL}${withQuery(path, query)}`, {
    ...rest,
    headers: {
      ...(rest.body && !(rest.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(actingGym ? { "X-Gym-ID": actingGym } : {}),
      ...headers,
    },
  });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, errorMessage(body, `Request failed (${res.status})`), body);
  return body as T;
}

export const get = <T,>(path: string, query?: Query) => api<T>(path, { query });
export const post = <T,>(path: string, body?: unknown, query?: Query) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body), query });
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const patch = <T,>(path: string, body?: unknown, query?: Query) =>
  api<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body), query });
export const del = (path: string) => api<void>(path, { method: "DELETE" });
