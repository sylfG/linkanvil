"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

// Las 6 keys de la policy de auditoría (migración 0007). El orden importa
// para la comparación con presets — el backend normaliza también el orden.
export const AUDIT_POLICY_KEYS = [
  "evento_pasado_alto",
  "evento_pasado_medio",
  "evento_pasado_nulo",
  "referencia_pasada_alto",
  "referencia_pasada_medio",
  "referencia_pasada_nulo",
] as const;

export type AuditPolicyKey = (typeof AUDIT_POLICY_KEYS)[number];
export type AuditDecision = "activo" | "cuarentena" | "expirado";
export type AuditPolicy = Record<AuditPolicyKey, AuditDecision>;
export type AuditPresetName = "estricto" | "equilibrado" | "permisivo";

// Presets canónicos. Deben coincidir bit-a-bit con el backend (db.py
// DEFAULT_AUDIT_POLICY y migración 0007) para que la comparación
// client-side detecte cuándo el usuario está sobre un preset puro.
export const AUDIT_PRESETS: Record<AuditPresetName, AuditPolicy> = {
  estricto: {
    evento_pasado_alto: "cuarentena",
    evento_pasado_medio: "cuarentena",
    evento_pasado_nulo: "cuarentena",
    referencia_pasada_alto: "cuarentena",
    referencia_pasada_medio: "cuarentena",
    referencia_pasada_nulo: "cuarentena",
  },
  equilibrado: {
    evento_pasado_alto: "expirado",
    evento_pasado_medio: "cuarentena",
    evento_pasado_nulo: "cuarentena",
    referencia_pasada_alto: "expirado",
    referencia_pasada_medio: "cuarentena",
    referencia_pasada_nulo: "cuarentena",
  },
  permisivo: {
    evento_pasado_alto: "expirado",
    evento_pasado_medio: "cuarentena",
    evento_pasado_nulo: "cuarentena",
    referencia_pasada_alto: "expirado",
    referencia_pasada_medio: "activo",
    referencia_pasada_nulo: "cuarentena",
  },
};

export const DEFAULT_AUDIT_POLICY: AuditPolicy = AUDIT_PRESETS.equilibrado;

/** Devuelve el nombre del preset que coincide exactamente con la policy,
 * o null si la policy ha sido modificada respecto a los 3 presets. */
export function matchPreset(policy: AuditPolicy): AuditPresetName | null {
  for (const name of Object.keys(AUDIT_PRESETS) as AuditPresetName[]) {
    const preset = AUDIT_PRESETS[name];
    let allEqual = true;
    for (const k of AUDIT_POLICY_KEYS) {
      if (preset[k] !== policy[k]) {
        allEqual = false;
        break;
      }
    }
    if (allEqual) return name;
  }
  return null;
}

export interface User {
  id: string;
  email: string;
  tenant_id: string;
  telegram_bot_active: boolean;
  created_at: string;
  // Migración 0007: policy JSONB por celda (6 keys). El backend siempre
  // devuelve las 6 keys, pero lo marcamos opcional para tolerar sesiones
  // de antes del deploy.
  audit_policy?: AuditPolicy;
  // Migración 0008: BYOK + flag demo.
  // - is_demo=true → ProfileModal oculta el formulario BYOK y muestra
  //   un info-box "cuenta compartida".
  // - llm_keys_configured=false → banner rojo "Sin claves no puedes
  //   ingestar/chatear". El chat además mapea 402 a este banner.
  is_demo?: boolean;
  llm_keys_configured?: boolean;
}

// Las 3 kinds de virtual-key que el backend espera en PUT /profile/llm-keys.
// Cualquier subset es válido (PATCH semántico). Si solo configuras `lite`,
// el backend la reusa para embeddings y pro vía fallback en resolve_llm_key.
export const LLM_KEY_KINDS = ["lite", "embeddings", "pro"] as const;
export type LLMKeyKind = (typeof LLM_KEY_KINDS)[number];

interface AuthState {
  token: string | null;
  user: User | null;
  setAuth: (token: string, user: User) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => set({ token, user }),
      clearAuth: () => set({ token: null, user: null }),
    }),
    { name: "cerebro-auth", skipHydration: false }
  )
);
