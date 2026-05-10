"use client";
import { useSSE } from "./sse";

export interface ResourceEvent {
  evento_tipo:
    | "recurso.cuarentena"
    | "recurso.expirado"
    | "recurso.rescatado";
  recurso_id?: string;
  url?: string;
  titulo?: string;
  motivo?: string;
  created_at?: string;
}

/**
 * Stream SSE de transiciones del ciclo de vida de recursos
 * (cuarentena, expirado, rescatado). El backend lo publica desde el
 * notifier-worker tras insertar la notificación.
 *
 * Cada vista que muestre recursos lo invoca y, en `onEvent`, dispara su
 * `load()` para refrescar. EventSource auto-reconecta nativamente.
 */
export function useResourceStream(
  token: string | null | undefined,
  onEvent?: (ev: ResourceEvent) => void,
) {
  const url = token
    ? `/api/resources/stream?token=${encodeURIComponent(token)}`
    : null;
  return useSSE<ResourceEvent>(url, onEvent);
}
