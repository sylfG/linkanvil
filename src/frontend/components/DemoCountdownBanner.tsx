"use client";

import { useEffect, useState } from "react";
import { Hourglass } from "lucide-react";
import { useAuthStore } from "@/lib/auth";

// Slice 6 — Componente extraído de (app)/layout.tsx para que tanto el
// layout como la vista /demo puedan importarlo desde un único origen.
//
// Comportamiento:
// - Lee `demo_session_expires_at` del store (ISO absoluto del backend).
// - Recalcula los segundos restantes cada 1s sin acumular drift
//   (resta a Date.now(), no contador incremental).
// - Pinta colores progresivos: accent (normal) → amber (≤60s) → red (=0).
// - A los 0s, dispara un GET /auth/me dummy para que el interceptor
//   global detecte el 401 demo_expired y redirija a /login.
// - Si el usuario no es demo o no hay timestamp → renderiza null.

export function DemoCountdownBanner() {
  const user = useAuthStore((s) => s.user);
  const token = useAuthStore((s) => s.token);
  const [remaining, setRemaining] = useState<number | null>(null);

  const expiresAt = user?.demo_session_expires_at
    ? new Date(user.demo_session_expires_at).getTime()
    : null;

  useEffect(() => {
    if (!user?.is_demo || !expiresAt) {
      setRemaining(null);
      return;
    }
    const tick = () => {
      const left = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
      setRemaining(left);
      if (left === 0 && token) {
        // El backend devuelve 401 demo_expired y api.ts redirige
        // automáticamente. Usamos /auth/me porque es el endpoint más
        // barato — solo decodifica el JWT y consulta una fila.
        const origin =
          typeof window !== "undefined" ? window.location.origin : "";
        fetch(`${origin}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
          credentials: "include",
        }).catch(() => {});
      }
    };
    tick();
    const iv = window.setInterval(tick, 1000);
    return () => window.clearInterval(iv);
  }, [user?.is_demo, expiresAt, token]);

  if (!user?.is_demo || remaining === null) return null;

  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");
  const isUrgent = remaining <= 60;
  const isCritical = remaining === 0;

  return (
    <div
      className={`relative z-30 text-xs px-4 py-1.5 flex items-center justify-center gap-2 border-b ${
        isCritical
          ? "bg-red-900/40 border-red-700/50 text-red-100"
          : isUrgent
            ? "bg-amber-900/30 border-amber-700/40 text-amber-100"
            : "bg-accent/10 border-accent/25 text-accent-light"
      }`}
    >
      <Hourglass
        className={`w-3.5 h-3.5 ${isUrgent ? "animate-pulse" : ""}`}
      />
      <span className="font-medium">Sesión demo</span>
      <span className="font-mono tracking-wider">
        {isCritical ? "Caducada" : `${mm}:${ss}`}
      </span>
      <span className="text-muted hidden sm:inline">
        {isCritical
          ? "Recarga para empezar otra"
          : "· se borrará todo lo que añadas al expirar"}
      </span>
    </div>
  );
}
