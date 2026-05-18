"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Sparkles, Clock, Hourglass, AlertTriangle, CalendarX,
  CheckCircle2, ArrowRight, MessageSquare, BookOpen, ListTree,
} from "lucide-react";
import Link from "next/link";

import { apiCall } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { DemoCountdownBanner } from "../layout";

// ----------------------------------------------------------------------------
// Tipos del payload de /demo/timeline (espejan src/api/models.py).
// ----------------------------------------------------------------------------
type TimelineKind =
  | "transition_cuarentena"
  | "transition_expirado"
  | "reminder_expiry_5min";

interface TimelineEvent {
  id: string;
  fires_at: string;          // ISO timestamp
  fired_at: string | null;   // null = pending
  kind: TimelineKind;
  recurso_id: string | null;
  motivo: string | null;
  description: string | null;
}

interface TimelinePayload {
  session: {
    tenant_id: string;
    created_at: string;
    expires_at: string;
  };
  events: TimelineEvent[];
}

// Etiqueta humana + icono por kind. Centralizado para que la lista + el
// chip "próximo evento" + los puntos SVG usen la misma representación.
const KIND_META: Record<
  TimelineKind,
  {
    label: string;
    color: string;
    bg: string;
    icon: typeof AlertTriangle;
  }
> = {
  transition_cuarentena: {
    label: "Cuarentena",
    color: "text-amber-300",
    bg: "bg-amber-900/30 border-amber-700/40",
    icon: AlertTriangle,
  },
  transition_expirado: {
    label: "Archivo",
    color: "text-rose-300",
    bg: "bg-rose-900/30 border-rose-700/40",
    icon: CalendarX,
  },
  reminder_expiry_5min: {
    label: "Recordatorio",
    color: "text-accent-light",
    bg: "bg-accent/10 border-accent/25",
    icon: Hourglass,
  },
};

function formatRelative(ms: number): string {
  if (ms <= 0) return "ya";
  const totalSec = Math.floor(ms / 1000);
  const mm = Math.floor(totalSec / 60);
  const ss = totalSec % 60;
  if (mm === 0) return `${ss}s`;
  return `${mm}:${String(ss).padStart(2, "0")}`;
}

// ----------------------------------------------------------------------------
// Layout principal
// ----------------------------------------------------------------------------

export default function DemoPage() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const [timeline, setTimeline] = useState<TimelinePayload | null>(null);
  const [tab, setTab] = useState<"timeline" | "kb" | "cuarentena" | "archivo" | "chat">(
    "timeline",
  );
  const [error, setError] = useState<string | null>(null);

  // Polling cada 5s para refrescar fired_at. Bajamos a 1s sería caro
  // (es un endpoint con un query JOIN); 5s es suficiente para que
  // el visitante vea el cambio "pending → disparado" después del audit.
  useEffect(() => {
    if (!token || !user?.is_demo) return;
    let cancelled = false;
    async function load() {
      try {
        const data = await apiCall<TimelinePayload>("/demo/timeline");
        if (!cancelled) {
          setTimeline(data);
          setError(null);
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "Error cargando timeline");
      }
    }
    load();
    const iv = window.setInterval(load, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(iv);
    };
  }, [token, user?.is_demo]);

  // El "próximo evento" = primer evento con fired_at=null. Para el
  // chip del header — comunica qué falta antes de que pase.
  const nextEvent = useMemo(() => {
    if (!timeline) return null;
    return timeline.events.find((e) => e.fired_at === null) ?? null;
  }, [timeline]);

  const [nowMs, setNowMs] = useState<number>(Date.now());
  useEffect(() => {
    const iv = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(iv);
  }, []);

  if (!user?.is_demo) {
    // El guard de layout ya redirige a /chat; este return es defensivo
    // para evitar un flash de contenido durante la transición.
    return null;
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Countdown reutilizado del banner global (Slice 5). */}
      <DemoCountdownBanner />

      {/* Header propio del /demo: chip de próximo evento + estado de la sesión. */}
      <header className="border-b border-border bg-surface/50">
        <div className="max-w-6xl mx-auto px-5 py-4 flex flex-col sm:flex-row gap-3 sm:items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-accent-light" />
            <h1 className="font-semibold text-slate-100">
              Demo público — sesión de 15 minutos
            </h1>
          </div>

          {nextEvent && (
            <button
              onClick={() => setTab("timeline")}
              className="group flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-surface transition-colors text-left"
              title="Ir al timeline"
            >
              <Clock className="w-3.5 h-3.5 text-accent-light" />
              <span className="text-xs text-muted">Próximo:</span>
              <span className="text-xs font-medium text-slate-200">
                {KIND_META[nextEvent.kind].label}
              </span>
              <span className="text-xs font-mono text-accent-light">
                en {formatRelative(new Date(nextEvent.fires_at).getTime() - nowMs)}
              </span>
              <ArrowRight className="w-3 h-3 text-muted group-hover:translate-x-0.5 transition-transform" />
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="max-w-6xl mx-auto px-5 flex gap-1 overflow-x-auto">
          {[
            { id: "timeline", label: "Timeline", icon: ListTree },
            { id: "kb", label: "Base de Conocimiento", icon: BookOpen },
            { id: "cuarentena", label: "Cuarentena", icon: AlertTriangle },
            { id: "archivo", label: "Archivo", icon: CalendarX },
            { id: "chat", label: "Chat", icon: MessageSquare },
          ].map((t) => {
            const Icon = t.icon;
            const active = tab === (t.id as typeof tab);
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id as typeof tab)}
                className={`flex items-center gap-2 px-3 py-2 text-xs whitespace-nowrap border-b-2 transition-colors ${
                  active
                    ? "border-accent-light text-slate-100"
                    : "border-transparent text-muted hover:text-slate-200"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {t.label}
              </button>
            );
          })}
        </div>
      </header>

      {/* Contenido del tab */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-5 py-6">
          {error && (
            <div className="mb-4 p-3 bg-red-900/30 border border-red-700/50 rounded-lg text-red-200 text-sm">
              {error}
            </div>
          )}

          {tab === "timeline" && timeline && (
            <TimelineTab timeline={timeline} nowMs={nowMs} />
          )}

          {tab !== "timeline" && (
            <PlaceholderTab
              kind={tab}
              tenantId={user.tenant_id}
            />
          )}
        </div>
      </main>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Timeline tab — la pieza central pedagógica
// ----------------------------------------------------------------------------

function TimelineTab({
  timeline,
  nowMs,
}: {
  timeline: TimelinePayload;
  nowMs: number;
}) {
  const startMs = new Date(timeline.session.created_at).getTime();
  const endMs = new Date(timeline.session.expires_at).getTime();
  const totalMs = endMs - startMs;

  // Cada evento posicionado proporcionalmente al rango [0, 100]%.
  const points = timeline.events.map((e) => {
    const t = new Date(e.fires_at).getTime();
    const pct = Math.min(
      100,
      Math.max(0, ((t - startMs) / totalMs) * 100),
    );
    return { ...e, pct };
  });

  const nowPct = Math.min(
    100,
    Math.max(0, ((nowMs - startMs) / totalMs) * 100),
  );

  return (
    <div className="space-y-6">
      {/* Encabezado pedagógico */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="font-semibold text-slate-100 mb-2 flex items-center gap-2">
          <ListTree className="w-4 h-4 text-accent-light" />
          Línea temporal de tu sesión
        </h2>
        <p className="text-sm text-muted leading-relaxed">
          Tu sesión de 15 minutos incluye 4 eventos programados que
          simulan, comprimido en el tiempo, cómo LinkAnvil aplica su
          ciclo de vida sobre los recursos. A los 5 minutos se dispara
          una <strong className="text-amber-300">auditoría</strong> que
          mueve 2 recursos a cuarentena y archiva 1 directamente. A los
          10 minutos te avisamos de que quedan 5.
        </p>
      </div>

      {/* Línea horizontal con puntos */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="relative h-20">
          {/* Eje base */}
          <div className="absolute left-0 right-0 top-1/2 h-0.5 bg-border" />

          {/* Progreso (now marker) */}
          <div
            className="absolute top-1/2 left-0 h-0.5 bg-accent-light/40"
            style={{ width: `${nowPct}%` }}
          />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-accent border-2 border-accent-light shadow-lg shadow-accent/50"
            style={{ left: `calc(${nowPct}% - 6px)` }}
            title="Ahora"
          />

          {/* Eventos */}
          {points.map((p) => {
            const meta = KIND_META[p.kind];
            const Icon = meta.icon;
            const fired = p.fired_at !== null;
            return (
              <div
                key={p.id}
                className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 flex flex-col items-center"
                style={{ left: `${p.pct}%` }}
              >
                <div
                  className={`flex items-center justify-center w-6 h-6 rounded-full border ${meta.bg} ${meta.color}`}
                  title={p.description ?? meta.label}
                >
                  {fired ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : (
                    <Icon className="w-3 h-3" />
                  )}
                </div>
                <span className="absolute top-7 text-[10px] text-muted whitespace-nowrap">
                  {new Date(p.fires_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Tabla de eventos */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Hora</th>
              <th className="text-left px-4 py-2 font-medium">Evento</th>
              <th className="text-left px-4 py-2 font-medium">Motivo</th>
              <th className="text-left px-4 py-2 font-medium">Descripción</th>
              <th className="text-left px-4 py-2 font-medium">Estado</th>
            </tr>
          </thead>
          <tbody>
            {timeline.events.map((e) => {
              const meta = KIND_META[e.kind];
              const fired = e.fired_at !== null;
              return (
                <tr
                  key={e.id}
                  className="border-t border-border/50 hover:bg-surface/40"
                >
                  <td className="px-4 py-2 font-mono text-xs">
                    {new Date(e.fires_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded border ${meta.bg} ${meta.color}`}
                    >
                      <meta.icon className="w-3 h-3" />
                      {meta.label}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-muted">
                    {e.motivo ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-200">
                    {e.description ?? "—"}
                  </td>
                  <td className="px-4 py-2">
                    {fired ? (
                      <span className="inline-flex items-center gap-1 text-xs text-green-300">
                        <CheckCircle2 className="w-3 h-3" />
                        Disparado
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-muted">
                        <Hourglass className="w-3 h-3" />
                        Pendiente
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Placeholder tabs (Slice 6.1 los implementará con datos reales)
// ----------------------------------------------------------------------------

function PlaceholderTab({
  kind,
  tenantId,
}: {
  kind: "kb" | "cuarentena" | "archivo" | "chat";
  tenantId: string;
}) {
  const COPY: Record<typeof kind, { title: string; body: string }> = {
    kb: {
      title: "Base de Conocimiento",
      body: "Aquí verás los 18 recursos seed compartidos del demo más los 3 efímeros que se stagearon al iniciar tu sesión.",
    },
    cuarentena: {
      title: "Cuarentena",
      body: "Recursos que el sistema mueve aquí cuando dejan de ser relevantes — caducidad, evento_pasado, manual. Al pasar 30 días sin rescate, expiran al archivo histórico.",
    },
    archivo: {
      title: "Archivo histórico",
      body: "Recursos expirados que se mantienen accesibles solo cuando activas el toggle 'Archivo' en el chat. Útiles para consulta histórica.",
    },
    chat: {
      title: "Chat con RAG",
      body: "Pregúntale al chat con tus palabras y verás las fuentes citadas de tu base de conocimiento.",
    },
  };

  const c = COPY[kind];

  return (
    <div className="bg-card border border-border rounded-xl p-8 text-center">
      <h2 className="font-semibold text-slate-100 mb-2">{c.title}</h2>
      <p className="text-sm text-muted leading-relaxed max-w-xl mx-auto mb-6">
        {c.body}
      </p>
      <p className="text-xs text-muted">
        Esta pestaña se conectará a las APIs del demo en la siguiente
        iteración. Por ahora, abre el Timeline para ver los eventos
        intra-sesión en vivo.
      </p>
      <p className="text-[10px] text-muted/60 mt-4 font-mono">
        tenant: {tenantId}
      </p>
    </div>
  );
}
