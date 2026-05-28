"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Sparkles, Clock, Hourglass, AlertTriangle, CalendarX,
  CheckCircle2, ListTree, BookOpen, MessageSquare, ArrowRight,
} from "lucide-react";

import { apiCall } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";

// Slice 6.2 — La vista `/demo` deja de ser el dashboard del demo (con
// tabs internas) y pasa a ser **una entrada más** del sidebar — la
// "Línea temporal" pedagógica que solo el demo puede consultar. El
// resto de la app (/chat, /kb, /quarantine, /expired, /ingest) son
// idénticas a las del usuario registrado; cambian solo los badges y
// tooltips que invitan a contextualizar las limitaciones del demo.

type TimelineKind =
  | "transition_cuarentena"
  | "transition_expirado"
  | "reminder_expiry_5min";

interface TimelineEvent {
  id: string;
  fires_at: string;
  fired_at: string | null;
  kind: TimelineKind;
  recurso_id: string | null;
  motivo: string | null;
  description: string | null;
}

interface TimelinePayload {
  session: { tenant_id: string; created_at: string; expires_at: string };
  events: TimelineEvent[];
}

const KIND_META: Record<
  TimelineKind,
  { label: string; color: string; bg: string; icon: typeof AlertTriangle }
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

export default function DemoTimelinePage() {
  const user = useAuthStore((s) => s.user);
  const token = useAuthStore((s) => s.token);
  const [timeline, setTimeline] = useState<TimelinePayload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Polling 5s para mostrar transiciones pending→disparado en vivo
  // después del audit del minuto 5. Endpoint barato (1 JOIN sobre
  // demo_session_events del propio tenant).
  useEffect(() => {
    if (!token || !user?.is_demo) return;
    let cancelled = false;
    async function load() {
      try {
        const data = await apiCall<TimelinePayload>("/demo/timeline");
        if (!cancelled) {
          setTimeline(data);
          setErr(null);
        }
      } catch (e: any) {
        if (!cancelled) setErr(e?.message ?? "Error cargando timeline");
      }
    }
    load();
    const iv = window.setInterval(load, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(iv);
    };
  }, [token, user?.is_demo]);

  const [nowMs, setNowMs] = useState<number>(Date.now());
  useEffect(() => {
    const iv = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(iv);
  }, []);

  const nextEvent = useMemo(() => {
    if (!timeline) return null;
    return timeline.events.find((e) => e.fired_at === null) ?? null;
  }, [timeline]);

  if (!user?.is_demo) return null; // guard defensivo (layout ya redirige)

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-5 md:px-8 py-6 space-y-6">
        {/* Header pedagógico */}
        <div className="bg-card border border-border rounded-xl p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h1 className="font-semibold text-slate-100 mb-1 flex items-center gap-2">
                <ListTree className="w-4 h-4 text-accent-light" />
                Línea temporal del demo
              </h1>
              <p className="text-sm text-muted leading-relaxed">
                Tu sesión de 15 minutos incluye 4 eventos programados
                que simulan, comprimido, cómo LinkAnvil aplica su ciclo
                de vida. A los <strong className="text-amber-300">5
                minutos</strong> se dispara una auditoría que mueve 2
                recursos a cuarentena y archiva 1 directamente. A los
                10 minutos te avisamos de que quedan 5.
              </p>
            </div>
            {nextEvent && (
              <div className="flex-shrink-0 flex flex-col items-end gap-1 text-right">
                <span className="text-[10px] uppercase tracking-wider text-muted">
                  Próximo evento
                </span>
                <div className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-accent-light" />
                  <span className="text-xs font-medium text-slate-200">
                    {KIND_META[nextEvent.kind].label}
                  </span>
                  <span className="text-xs font-mono text-accent-light">
                    en {formatRelative(new Date(nextEvent.fires_at).getTime() - nowMs)}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        {err && (
          <div className="p-3 bg-red-900/30 border border-red-700/50 rounded-lg text-red-200 text-sm">
            {err}
          </div>
        )}

        {timeline && (
          <>
            <TimelineSvg timeline={timeline} nowMs={nowMs} />
            <TimelineTable events={timeline.events} />
            <DemoCtaRow />
          </>
        )}
      </div>
    </div>
  );
}

function TimelineSvg({
  timeline,
  nowMs,
}: {
  timeline: TimelinePayload;
  nowMs: number;
}) {
  const startMs = new Date(timeline.session.created_at).getTime();
  const endMs = new Date(timeline.session.expires_at).getTime();
  const totalMs = endMs - startMs;
  const points = timeline.events.map((e) => {
    const t = new Date(e.fires_at).getTime();
    const pct = Math.min(100, Math.max(0, ((t - startMs) / totalMs) * 100));
    return { ...e, pct };
  });
  const nowPct = Math.min(
    100,
    Math.max(0, ((nowMs - startMs) / totalMs) * 100),
  );

  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <div className="relative h-20">
        <div className="absolute left-0 right-0 top-1/2 h-0.5 bg-border" />
        <div
          className="absolute top-1/2 left-0 h-0.5 bg-accent-light/40"
          style={{ width: `${nowPct}%` }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-accent border-2 border-accent-light shadow-lg shadow-accent/50"
          style={{ left: `calc(${nowPct}% - 6px)` }}
          title="Ahora"
        />
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
  );
}

function TimelineTable({ events }: { events: TimelineEvent[] }) {
  return (
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
          {events.map((e) => {
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
  );
}

// Atajos a las vistas reales de la app — el demo usa los mismos
// /chat, /kb, etc. que un usuario registrado. Este bloque les recuerda
// "después del audit, mira en Cuarentena/Archivo cómo aparecen los
// recursos transicionados".
function DemoCtaRow() {
  const items = [
    {
      href: "/chat",
      icon: MessageSquare,
      title: "Chatea con tu KB",
      desc: "Pregunta al RAG. Cita las fuentes recuperadas.",
    },
    {
      href: "/kb",
      icon: BookOpen,
      title: "Explora tu KB",
      desc: "18 seed + 3 efímeros sembrados al login.",
    },
    {
      href: "/quarantine",
      icon: AlertTriangle,
      title: "Cuarentena",
      desc: "Al minuto 5 verás 2 nuevos aquí.",
    },
    {
      href: "/expired",
      icon: CalendarX,
      title: "Archivo",
      desc: "Al minuto 5 verás 1 nuevo aquí.",
    },
  ];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      {items.map(({ href, icon: Icon, title, desc }) => (
        <Link
          key={href}
          href={href}
          className="group bg-card hover:bg-surface border border-border rounded-xl p-4 transition-colors"
        >
          <div className="flex items-center gap-2 mb-1">
            <Icon className="w-4 h-4 text-accent-light" />
            <span className="font-medium text-sm text-slate-100">
              {title}
            </span>
            <ArrowRight className="w-3 h-3 ml-auto text-muted group-hover:translate-x-0.5 transition-transform" />
          </div>
          <p className="text-xs text-muted leading-relaxed">{desc}</p>
        </Link>
      ))}
    </div>
  );
}
