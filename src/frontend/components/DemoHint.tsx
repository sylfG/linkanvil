"use client";

import { useState } from "react";
import { Info, Sparkles } from "lucide-react";
import { useAuthStore } from "@/lib/auth";

// Slice 6.2 — Hint pedagógico inline para sesiones demo.
//
// Renderiza un icono `Info` discreto al lado del elemento al que se
// adjunta. Al hover muestra un tooltip con copy explicativo de qué
// hace el demo distinto en ese lugar concreto (cuota, comportamiento
// del seed, recurso efímero, etc).
//
// Si el usuario NO es demo → renderiza null. Esto permite sembrar el
// componente en las vistas reales sin tocar el render para registered
// (cero ruido visual).
//
// Por qué un componente y no aria-describedby + CSS plano: queremos
// que el hint se vea SIEMPRE (no solo al focus de teclado), incluso
// en mobile (tap → toggle). Tailwind tooltips puros con :hover dejan
// mobile fuera y son menos accesibles.

interface DemoHintProps {
  /** Texto del tooltip — explica la limitación o comportamiento. */
  hint: string;
  /** Variante visual: 'info' (defecto) o 'sparkle' (acentuado). */
  variant?: "info" | "sparkle";
  /** Alineación del tooltip relativo al trigger. */
  align?: "left" | "right";
  /** Texto opcional acompañando el icono (chip mode). */
  label?: string;
}

export function DemoHint({
  hint,
  variant = "info",
  align = "left",
  label,
}: DemoHintProps) {
  const isDemo = useAuthStore((s) => !!s.user?.is_demo);
  const [open, setOpen] = useState(false);
  if (!isDemo) return null;

  const Icon = variant === "sparkle" ? Sparkles : Info;

  return (
    <span className="relative inline-flex items-center">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        aria-label="Información sobre el demo"
        className={`inline-flex items-center gap-1 ${
          label
            ? "px-2 py-0.5 rounded-full border border-accent/30 bg-accent/10 text-accent-light text-[10px] uppercase tracking-wider"
            : "p-0.5 rounded-full text-accent-light hover:text-accent-light/80"
        }`}
      >
        <Icon className="w-3 h-3" />
        {label && <span>{label}</span>}
      </button>
      {open && (
        <span
          role="tooltip"
          className={`absolute top-full mt-1.5 z-50 w-64 p-2.5 text-[11px] leading-relaxed rounded-lg border border-accent/30 bg-bg shadow-xl text-slate-200 ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          <span className="block font-medium text-accent-light mb-1 flex items-center gap-1">
            <Sparkles className="w-3 h-3" />
            Demo
          </span>
          {hint}
        </span>
      )}
    </span>
  );
}
