"use client";

// Slice 6 — Helper de arranque de sesión demo desde la landing.
//
// Llama a POST /auth/demo-start (sin password), recibe access_token +
// metadata de la sesión efímera, y hace POST a /auth/me para hidratar
// el store de auth. Devuelve el user object para que el caller decida
// el redirect (típicamente router.push("/demo")).
//
// Por qué un módulo separado (y no inline en Hero/CTABanner):
//   1. Tres CTAs distintas en la landing necesitan disparar este flujo.
//   2. El error handling y el setAuth son idénticos en los tres sitios.
//   3. Mantener el side-effect (mutación del store) en un único lugar
//      facilita debug si el flujo se rompe.

import { apiCall } from "@/lib/api";
import { useAuthStore, type User } from "@/lib/auth";

interface DemoStartResponse {
  access_token: string;
  token_type: string;
  csrf_token: string;
  redirect: string;     // "/demo" — el backend dicta el destino canónico
  tenant_id: string;
  expires_at: string;   // ISO timestamptz
}

/**
 * Arranca una sesión demo nueva. Lanza Error con un mensaje legible si
 * el backend rechaza (503 demo_unavailable, 429 rate limit, etc).
 * El caller debe hacer el `router.push(response.redirect)` tras
 * resolverse — este helper NO navega para no acoplar redirects a Next.js.
 */
export async function startDemoSession(): Promise<{
  user: User;
  redirect: string;
  expires_at: string;
}> {
  const res = await apiCall<DemoStartResponse>("/auth/demo-start", {
    method: "POST",
    body: JSON.stringify({}),
  });

  // Tras /demo-start el backend ya seteó la cookie cerebro-session;
  // /auth/me valida y devuelve el user con tenant_id efímero +
  // demo_session_expires_at relleno (el countdown banner lo lee
  // directamente del store).
  const me = await apiCall<User>("/auth/me", {}, res.access_token);

  useAuthStore.getState().setAuth(res.access_token, me);

  return {
    user: me,
    redirect: res.redirect || "/demo",
    expires_at: res.expires_at,
  };
}
