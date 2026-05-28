export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const DEFAULT_TIMEOUT_MS = 12000;

export function authHeaders(extra: Record<string, string> = {}) {
  const token = localStorage.getItem("gymflow-token");
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

export function apiFetch(path: string, init: RequestInit = {}) {
  const extraHeaders = init.headers instanceof Headers
    ? Object.fromEntries(init.headers.entries())
    : Array.isArray(init.headers)
      ? Object.fromEntries(init.headers)
      : (init.headers as Record<string, string> | undefined) ?? {};
  const signal = init.signal ?? (
    typeof AbortSignal !== "undefined" && "timeout" in AbortSignal
      ? AbortSignal.timeout(DEFAULT_TIMEOUT_MS)
      : undefined
  );
  return fetch(`${API_URL}${path}`, {
    ...init,
    signal,
    headers: authHeaders(extraHeaders),
  });
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${path}`);
  }
  return response.json();
}

export async function getJsonOr<T>(path: string, fallback: T): Promise<T> {
  try {
    return await getJson<T>(path);
  } catch {
    return fallback;
  }
}
