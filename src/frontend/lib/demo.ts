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
  /** Slice 6.3: true si la IP ya tenía una sesión viva y se ha
   *  reutilizado (no se ha creado una nueva). */
  resumed?: boolean;
  seconds_remaining?: number;
}

/**
 * Arranca una sesión demo nueva. Lanza Error con un mensaje legible si
 * el backend rechaza (503 demo_unavailable, 429 rate limit, etc).
 *
 * Slice 6.3 — el backend impone "1 demo por IP por día UTC":
 *   - Si esta IP ya tiene una sesión viva → re-emite cookies y devuelve
 *     `resumed: true` con los segundos que quedan.
 *   - Si esta IP gastó su demo hoy (sesión expirada) → 429 con el
 *     mensaje `demo_already_used_today`, que propagamos como Error
 *     legible para que la landing lo muestre directamente.
 *
 * El caller decide el redirect (típicamente `router.push(response.redirect)`).
 */
export async function startDemoSession(): Promise<{
  user: User;
  redirect: string;
  expires_at: string;
  resumed: boolean;
}> {
  let res: DemoStartResponse;
  try {
    res = await apiCall<DemoStartResponse>("/auth/demo-start", {
      method: "POST",
      body: JSON.stringify({}),
    });
  } catch (err: any) {
    // apiCall vuelca `detail` en err.message como JSON cuando el
    // backend usa HTTPException con cuerpo estructurado. Lo
    // desempaquetamos para que el visitante vea el copy del backend
    // sin ruido de JSON crudo.
    const raw = err?.message ?? "";
    try {
      const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
      if (parsed?.message) throw new Error(parsed.message);
      if (parsed?.error) throw new Error(parsed.error);
    } catch (parseErr: any) {
      // Si el throw nuestro es lo que cayó aquí, propágalo tal cual.
      if (parseErr instanceof Error && parseErr !== err) throw parseErr;
      // Si no parseaba, devuelve el message original.
    }
    throw err;
  }

  const me = await apiCall<User>("/auth/me", {}, res.access_token);
  useAuthStore.getState().setAuth(res.access_token, me);

  return {
    user: me,
    redirect: res.redirect || "/demo",
    expires_at: res.expires_at,
    resumed: !!res.resumed,
  };
}
