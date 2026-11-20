"use client";

import { useEffect, useState } from "react";
import { getRole } from "@/services/api";
import type { Role } from "@/types";

/** Current user's role from the session cookie (null until mounted, to avoid hydration mismatches). */
export function useRole(): Role | null {
  const [role, setRole] = useState<Role | null>(null);
  useEffect(() => setRole(getRole() as Role | null), []);
  return role;
}
