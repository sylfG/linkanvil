"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Sparkles, Clock, Hourglass, AlertTriangle, CalendarX,
  CheckCircle2, ArrowRight, MessageSquare, BookOpen, ListTree,
  Send, Loader2, RefreshCw, ExternalLink, Bot, User,
} from "lucide-react";

import { API_URL, apiCall } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { DemoCountdownBanner } from "@/components/DemoCountdownBanner";

// ----------------------------------------------------------------------------
// Tipos del payload de /demo/timeline (espejan src/api/models.py).
// ----------------------------------------------------------------------------
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
  session: {
    tenant_id: string;
    created_at: string;
    expires_at: string;
  };
  events: TimelineEvent[];
}

interface Resource {
  id: string;
  url: string;
  titulo?: string;
  resumen?: string;
  categoria?: string;
  estado: string;
  fecha_caducidad?: string | null;
  quarantine_reason?: string | null;
  quarantine_grace_until?: string | null;
  created_at?: string;
}

// Etiqueta humana + icono por kind del evento. Usado por timeline + chip.
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

type TabId = "timeline" | "kb" | "cuarentena" | "archivo" | "chat";

// ----------------------------------------------------------------------------
// Página principal del demo
// ----------------------------------------------------------------------------

export default function DemoPage() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const [timeline, setTimeline] = useState<TimelinePayload | null>(null);
  const [tab, setTab] = useState<TabId>("timeline");
  const [error, setError] = useState<string | null>(null);

  // Polling cada 5s para refrescar fired_at. Endpoint barato (un JOIN sobre
  // demo_session_events del propio tenant) y suficiente granularidad para
  // mostrar la transición pending→disparado en vivo tras el audit.
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

  const nextEvent = useMemo(() => {
    if (!timeline) return null;
    return timeline.events.find((e) => e.fired_at === null) ?? null;
  }, [timeline]);

  const [nowMs, setNowMs] = useState<number>(Date.now());
  useEffect(() => {
    const iv = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(iv);
  }, []);

  if (!user?.is_demo) return null; // guard defensivo (el layout ya redirige)

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <DemoCountdownBanner />

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

        <div className="max-w-6xl mx-auto px-5 flex gap-1 overflow-x-auto">
          {[
            { id: "timeline" as TabId, label: "Timeline", icon: ListTree },
            { id: "kb" as TabId, label: "Base de Conocimiento", icon: BookOpen },
            { id: "cuarentena" as TabId, label: "Cuarentena", icon: AlertTriangle },
            { id: "archivo" as TabId, label: "Archivo", icon: CalendarX },
            { id: "chat" as TabId, label: "Chat", icon: MessageSquare },
          ].map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
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
          {tab === "kb" && <ResourceListTab kind="kb" />}
          {tab === "cuarentena" && <ResourceListTab kind="cuarentena" />}
          {tab === "archivo" && <ResourceListTab kind="archivo" />}
          {tab === "chat" && <ChatTab />}
        </div>
      </main>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Timeline tab
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
    <div className="space-y-6">
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
// ResourceListTab — KB / Cuarentena / Archivo
// ----------------------------------------------------------------------------

interface ResourceTabConfig {
  endpoint: string;          // path absoluto a apiCall
  title: string;
  blurb: string;
  emptyMsg: string;
  badgeLabel: (r: Resource) => string;
  badgeClass: string;
  unwrap: (raw: unknown) => Resource[];
}

const RESOURCE_TABS: Record<"kb" | "cuarentena" | "archivo", ResourceTabConfig> = {
  kb: {
    endpoint: "/resources?estado=activo&limit=100",
    title: "Base de Conocimiento",
    blurb:
      "Recursos activos del demo. Verás los 18 seed compartidos por todos los visitantes más los 3 efímeros que se stagearon al iniciar tu sesión.",
    emptyMsg: "Tu KB está vacía.",
    badgeLabel: () => "Activo",
    badgeClass: "bg-green-900/30 border-green-700/40 text-green-300",
    unwrap: (raw) => (Array.isArray(raw) ? (raw as Resource[]) : []),
  },
  cuarentena: {
    endpoint: "/resources/quarantine?limit=100",
    title: "Cuarentena",
    blurb:
      "Recursos puestos en cuarentena automáticamente (audit cron) o manualmente. Tras 30 días sin rescate expiran al archivo histórico.",
    emptyMsg:
      "No hay recursos en cuarentena. Espera al minuto 5 — el audit del demo moverá 2 aquí.",
    badgeLabel: (r) => r.quarantine_reason ?? "cuarentena",
    badgeClass: "bg-amber-900/30 border-amber-700/40 text-amber-300",
    unwrap: (raw) => {
      const obj = raw as { items?: Resource[] } | Resource[];
      if (Array.isArray(obj)) return obj;
      return obj.items ?? [];
    },
  },
  archivo: {
    endpoint: "/resources/expired?limit=100",
    title: "Archivo histórico",
    blurb:
      "Recursos expirados — visibles aquí y opt-in en el chat con el toggle 'Archivo'. El demo archiva 1 directamente al minuto 5 vía auto_archive.",
    emptyMsg:
      "No hay archivo todavía. Espera al minuto 5 — el audit demo archiva 1 recurso directo.",
    badgeLabel: () => "Expirado",
    badgeClass: "bg-rose-900/30 border-rose-700/40 text-rose-300",
    unwrap: (raw) => {
      const obj = raw as { items?: Resource[] } | Resource[];
      if (Array.isArray(obj)) return obj;
      return obj.items ?? [];
    },
  },
};

function ResourceListTab({ kind }: { kind: "kb" | "cuarentena" | "archivo" }) {
  const cfg = RESOURCE_TABS[kind];
  const [items, setItems] = useState<Resource[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const raw = await apiCall<unknown>(cfg.endpoint);
      setItems(cfg.unwrap(raw));
    } catch (e: any) {
      setErr(e?.message ?? "Error cargando recursos");
    }
  }, [cfg]);

  // Recarga cada 10s para que las transiciones del audit del demo
  // aparezcan en estas listas sin tener que cambiar de tab.
  useEffect(() => {
    load();
    const iv = window.setInterval(load, 10000);
    return () => window.clearInterval(iv);
  }, [load, reloadKey]);

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-xl p-5 flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-slate-100 mb-1">{cfg.title}</h2>
          <p className="text-sm text-muted leading-relaxed">{cfg.blurb}</p>
        </div>
        <button
          onClick={() => setReloadKey((k) => k + 1)}
          className="flex-shrink-0 p-2 rounded-lg border border-border bg-surface hover:bg-card text-muted hover:text-slate-200 transition-colors"
          title="Recargar"
          aria-label="Recargar lista"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {err && (
        <div className="p-3 bg-red-900/30 border border-red-700/50 rounded-lg text-red-200 text-sm">
          {err}
        </div>
      )}

      {items === null && !err && (
        <div className="bg-card border border-border rounded-xl p-8 text-center text-sm text-muted">
          <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
          Cargando...
        </div>
      )}

      {items !== null && items.length === 0 && !err && (
        <div className="bg-card border border-border rounded-xl p-8 text-center text-sm text-muted">
          {cfg.emptyMsg}
        </div>
      )}

      {items !== null && items.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {items.map((r) => (
            <article
              key={r.id}
              className="bg-card border border-border rounded-xl p-4 flex flex-col gap-2"
            >
              <div className="flex items-start gap-2">
                <h3 className="font-medium text-sm text-slate-100 line-clamp-2 flex-1">
                  {r.titulo || r.url}
                </h3>
                <span
                  className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 border rounded ${cfg.badgeClass} whitespace-nowrap`}
                >
                  {cfg.badgeLabel(r)}
                </span>
              </div>
              {r.resumen && (
                <p className="text-xs text-muted line-clamp-3 leading-relaxed">
                  {r.resumen}
                </p>
              )}
              <div className="flex items-center justify-between gap-2 mt-1">
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-accent-light/80 hover:underline truncate max-w-[70%] inline-flex items-center gap-1"
                  title={r.url}
                >
                  <ExternalLink className="w-3 h-3 flex-shrink-0" />
                  {r.url}
                </a>
                {r.categoria && (
                  <span className="text-[10px] text-muted">{r.categoria}</span>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------
// ChatTab — streaming sobre POST /chat
// ----------------------------------------------------------------------------

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  sources?: { title?: string; url?: string; score?: number }[];
}

function ChatTab() {
  const token = useAuthStore((s) => s.token);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 1e9, behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    setErr(null);

    const newConversation: ChatMsg[] = [
      ...messages,
      { role: "user", content: text },
      { role: "assistant", content: "" },
    ];
    setMessages(newConversation);
    setStreaming(true);

    try {
      const csrf =
        typeof document !== "undefined"
          ? ([...document.cookie.matchAll(/(?:^|; )cerebro_csrf=([^;]*)/g)]
              .pop()?.[1] ?? "")
          : "";
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {}),
        },
        body: JSON.stringify({
          messages: newConversation
            .slice(0, -1) // sin el placeholder del assistant
            .map((m) => ({ role: m.role, content: m.content })),
          model: "cerebro-lite",
          use_rag: true,
          include_archive: false,
        }),
      });

      if (res.status === 429) {
        const detail = await res.json().catch(() => null);
        throw new Error(
          detail?.detail?.message ??
            "El demo alcanzó su cuota diaria de chats. Regístrate para uso ilimitado.",
        );
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body!.getReader();
      const dec = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]") break;
          try {
            const parsed = JSON.parse(raw);
            if (parsed.type === "sources") {
              setMessages((prev) => {
                const u = [...prev];
                u[u.length - 1] = {
                  ...u[u.length - 1],
                  sources: parsed.sources,
                };
                return u;
              });
              continue;
            }
            if (parsed.type === "error") {
              throw new Error(parsed.message || "Error en el modelo");
            }
            const delta = parsed?.choices?.[0]?.delta?.content ?? "";
            if (delta) {
              setMessages((prev) => {
                const u = [...prev];
                u[u.length - 1] = {
                  ...u[u.length - 1],
                  content: u[u.length - 1].content + delta,
                };
                return u;
              });
            }
          } catch {
            /* chunk parse error — ignoramos */
          }
        }
      }
    } catch (e: any) {
      setErr(e?.message ?? "Error en el chat");
      // Quita el placeholder vacío del assistant si no se rellenó.
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role === "assistant" && !last.content) return prev.slice(0, -1);
        return prev;
      });
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="space-y-3 flex flex-col h-[calc(100vh-260px)] min-h-[420px]">
      <div className="bg-card border border-border rounded-xl p-4 flex-shrink-0">
        <h2 className="font-semibold text-slate-100 mb-1 flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-accent-light" />
          Chat con tu base de conocimiento
        </h2>
        <p className="text-sm text-muted leading-relaxed">
          Pregunta lo que quieras sobre los 18 recursos seed del demo
          (eventos, papers, repos, tutoriales) — el sistema busca en
          los chunks vectoriales y cita las fuentes. Cuota: 20 chats/día
          por IP.
        </p>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto bg-card border border-border rounded-xl p-4 space-y-3"
      >
        {messages.length === 0 && (
          <div className="text-center text-sm text-muted py-12">
            <Bot className="w-6 h-6 mx-auto mb-2 opacity-50" />
            Escribe una pregunta para empezar. Por ejemplo:
            <p className="mt-2 text-xs italic">
              "¿Qué papers de arXiv tengo en mi KB?" o "Resume el repo de
              Whisper".
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <ChatBubble key={i} msg={m} />
        ))}
        {streaming && messages[messages.length - 1]?.content === "" && (
          <div className="text-xs text-muted px-2 flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" /> generando...
          </div>
        )}
      </div>

      {err && (
        <div className="p-2 bg-red-900/30 border border-red-700/50 rounded-lg text-red-200 text-xs">
          {err}
        </div>
      )}

      <div className="flex gap-2 flex-shrink-0">
        <input
          type="text"
          value={input}
          disabled={streaming}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="Pregunta sobre tu KB..."
          className="flex-1 bg-surface border border-border rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-muted outline-none focus:border-accent-light transition-colors disabled:opacity-60"
        />
        <button
          onClick={() => void send()}
          disabled={!input.trim() || streaming}
          className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2.5 rounded-lg transition-colors flex items-center gap-2"
        >
          {streaming ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
        </button>
      </div>
    </div>
  );
}

function ChatBubble({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === "user";
  return (
    <div
      className={`flex gap-2 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-accent/20 border border-accent/30 flex items-center justify-center flex-shrink-0">
          <Bot className="w-3.5 h-3.5 text-accent-light" />
        </div>
      )}
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm ${
          isUser
            ? "bg-accent text-white"
            : "bg-surface border border-border text-slate-100"
        }`}
      >
        <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
        {msg.sources && msg.sources.length > 0 && (
          <div className="mt-2 pt-2 border-t border-border/30 space-y-1">
            <div className="text-[10px] uppercase tracking-wider text-muted">
              Fuentes ({msg.sources.length})
            </div>
            {msg.sources.slice(0, 4).map((s, i) => (
              <a
                key={i}
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block text-[11px] text-accent-light hover:underline truncate"
                title={s.url}
              >
                · {s.title || s.url}
                {typeof s.score === "number" && (
                  <span className="text-muted ml-1">
                    ({s.score.toFixed(2)})
                  </span>
                )}
              </a>
            ))}
          </div>
        )}
      </div>
      {isUser && (
        <div className="w-7 h-7 rounded-full bg-card border border-border flex items-center justify-center flex-shrink-0">
          <User className="w-3.5 h-3.5 text-muted" />
        </div>
      )}
    </div>
  );
}
