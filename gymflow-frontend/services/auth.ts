import type { Role, TokenResponse, User } from "@/types";
import { post, ROLE_COOKIE, TOKEN_COOKIE } from "./api";
import { setActingGymId } from "./tenant";

const MAX_AGE = 60 * 60 * 24; // matches ACCESS_TOKEN_EXPIRE_MINUTES on the API

function setCookie(name: string, value: string, maxAge: number) {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; Max-Age=${maxAge}; SameSite=Lax${secure}`;
}

function persist(res: TokenResponse) {
  setCookie(TOKEN_COOKIE, res.access_token, MAX_AGE);
  setCookie(ROLE_COOKIE, res.user.role, MAX_AGE);
  return res.user;
}

export function homeFor(role: Role): string {
  switch (role) {
    case "platform_admin":
      return "/platform/admin/dashboard";
    case "member":
      return "/member/dashboard";
    case "trainer":
      return "/dashboard/members";
    default:
      return "/dashboard/overview";
  }
}

export async function login(email: string, password: string): Promise<User> {
  return persist(await post<TokenResponse>("/auth/login", { email, password }));
}

export interface RegisterInput {
  gym_name: string;
  owner_name: string;
  email: string;
  password: string;
  phone?: string;
  city?: string;
  referral_code?: string;
}

export async function register(input: RegisterInput): Promise<User> {
  return persist(await post<TokenResponse>("/auth/register", input));
}

export function requestPasswordReset(email: string) {
  return post<{ detail: string }>("/auth/forgot-password", { email });
}

export function logout() {
  setCookie(TOKEN_COOKIE, "", 0);
  setCookie(ROLE_COOKIE, "", 0);
  setActingGymId(null);
  window.location.href = "/login";
}

/** One-click "See a live demo gym": the API only ever issues a token for the flagged demo tenant. */
export async function demoLogin(): Promise<User> {
  return persist(await post<TokenResponse>("/auth/demo-login"));
}

export async function resetPassword(token: string, password: string): Promise<User> {
  return persist(await post<TokenResponse>("/auth/reset-password", { token, password }));
}
