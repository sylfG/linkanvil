// All requests go to /api/* which Next.js proxies to cerebro-api:8001.
// The browser never calls port 8001 directly — no CORS issues, and
// the httpOnly session cookie set by the API is same-origin too.
const API_PREFIX = "/api";

const STATE_CHANGING = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const CSRF_COOKIE = "cerebro_csrf";
const CSRF_HEADER = "X-CSRF-Token";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const matches = [...document.cookie.matchAll(new RegExp("(?:^|; )" + name + "=([^;]*)", "g"))];
  return matches.length > 0 ? decodeURIComponent(matches[matches.length - 1][1]) : null;
}

// ── refresh-token coordination ────────────────────────────────────────────────
// A single in-flight /auth/refresh call serves every concurrent 401: without
// the mutex, the first response rotates the refresh cookie and invalidates
// the request the others depend on.

let refreshInFlight: Promise<boolean> | null = null;

async function performRefresh(): Promise<boolean> {
  const csrf = readCookie(CSRF_COOKIE);
  const res = await fetch(`${API_PREFIX}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { [CSRF_HEADER]: csrf } : {}),
    },
  });
  if (!res.ok) return false;
  // Sync the legacy Zustand token with the freshly minted JWT so the
  // Authorization-header fallback path stays in lockstep with the cookie.
  try {
    const body = await res.json();
    if (body?.access_token && typeof window !== "undefined") {
      const mod = await import("./auth");
      const state = mod.useAuthStore.getState();
      if (state.user) state.setAuth(body.access_token, state.user);
    }
  } catch {
    /* response body is optional */
  }
  return true;
}

async function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function forceLogout(): Promise<void> {
  if (typeof window === "undefined") return;
  try {
    const mod = await import("./auth");
    mod.useAuthStore.getState().clearAuth();
  } catch {
    /* hard-fail logout still redirects */
  }
  if (!window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}

// Exposed because the chat page calls fetch() directly for streaming and
// needs the same 401-recovery semantics.
export async function handleAuthFailure(res: Response): Promise<"refreshed" | "logout"> {
  if (res.status !== 401) return "logout";
  const reason = res.headers.get("X-Auth-Reason");
  // Only "expired" is recoverable. "invalid", "missing", "no_user",
  // "refresh_invalid" — terminal, drop straight to login.
  if (reason !== "expired") {
    await forceLogout();
    return "logout";
  }
  const ok = await tryRefresh();
  if (!ok) {
    await forceLogout();
    return "logout";
  }
  return "refreshed";
}

// ── apiCall ───────────────────────────────────────────────────────────────────

function buildHeaders(
  options: RequestInit,
  token?: string | null,
  method: string = "GET",
): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string>),
  };
  if (STATE_CHANGING.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers[CSRF_HEADER] = csrf;
  }
  return headers;
}

export async function apiCall<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();

  const doFetch = async (): Promise<Response> =>
    fetch(`${API_PREFIX}${path}`, {
      ...options,
      headers: buildHeaders(options, token, method),
      credentials: "include",
    });

  let res = await doFetch();

  if (res.status === 401) {
    const outcome = await handleAuthFailure(res);
    if (outcome === "logout") {
      throw new Error("Sesión expirada");
    }
    // Pull the rotated token from the Zustand store for the retry,
    // since the original `token` argument is now stale.
    let retryToken: string | null | undefined = token;
    if (typeof window !== "undefined") {
      try {
        const mod = await import("./auth");
        retryToken = mod.useAuthStore.getState().token ?? token;
      } catch {
        /* keep the original token */
      }
    }
    res = await fetch(`${API_PREFIX}${path}`, {
      ...options,
      headers: buildHeaders(options, retryToken, method),
      credentials: "include",
    });
    if (res.status === 401) {
      await forceLogout();
      throw new Error("Sesión expirada");
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    // FastAPI `HTTPException(status, dict)` devuelve detail como objeto
    // (ej: { error, op, message } en 402/429 BYOK/quota). Si lo pasamos
    // tal cual a `new Error()` el message acaba siendo "[object Object]".
    // Extraemos .message del detail estructurado y exponemos el objeto
    // crudo en error.detail por si el caller quiere ramificar por
    // error.detail.error (ej: "byok_required" vs "demo_daily_quota_exceeded").
    const detail = err.detail;
    let msg: string;
    if (typeof detail === "string") {
      msg = detail;
    } else if (detail && typeof detail === "object" && typeof detail.message === "string") {
      msg = detail.message;
    } else {
      msg = `HTTP ${res.status}`;
    }
    const error = new Error(msg) as Error & { detail?: unknown; status?: number };
    error.detail = detail;
    error.status = res.status;
    throw error;
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
