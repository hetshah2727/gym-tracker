"use client";

import type { User } from "@/types";
import { useApi } from "./useApi";

export function useAuth() {
  const { data: user, loading, error } = useApi<User>("/auth/me");
  return { user, loading, error };
}
