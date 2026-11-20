// Platform admins can "act as" a gym; the chosen gym id is sent as X-Gym-ID.
const KEY = "gf_acting_gym";

export function getActingGymId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setActingGymId(gymId: string | null) {
  try {
    if (gymId) window.localStorage.setItem(KEY, gymId);
    else window.localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable */
  }
}
