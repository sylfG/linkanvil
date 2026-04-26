// All requests go to /api/* which Next.js proxies to cerebro-api:8001.
// The browser never calls port 8001 directly — no CORS issues, and
// the httpOnly session cookie set by the API is same-origin too.
const API_PREFIX = "/api";

const STATE_CHANGING = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const CSRF_COOKIE = "cerebro_csrf";
const CSRF_HEADER = "X-CSRF-Token";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : null;
}

export async function apiCall<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    // Bearer is the legacy fallback during migration; the cookie sent
    // automatically (credentials: include) is the primary credential.
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string>),
  };

  if (STATE_CHANGING.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers[CSRF_HEADER] = csrf;
  }

  const res = await fetch(`${API_PREFIX}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// SSE: cookies travel automatically with EventSource on same origin,
// so the legacy ?token= query param is no longer required when the
// session cookie is present. Kept as a fallback for tools without a
// browser cookie jar.
export function sseUrl(token?: string | null) {
  if (token) {
    return `${API_PREFIX}/ingest/stream?token=${encodeURIComponent(token)}`;
  }
  return `${API_PREFIX}/ingest/stream`;
}

// Exposed for the chat page which uses fetch() directly for streaming.
export const API_PREFIX_EXPORT = API_PREFIX;
export { API_PREFIX as API_URL };
