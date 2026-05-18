"use client";
import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Link2, Plus, CheckCircle2, Loader2, AlertCircle, Trash2, Sparkles } from "lucide-react";
import { DemoHint } from "@/components/DemoHint";
import { apiCall, sseUrl } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { useSSE, type IngestEvent } from "@/lib/sse";

interface Procesando {
  id?: string;        // id de Postgres si ya se insertó el placeholder
  url: string;
  titulo?: string;
  status: string;     // mensaje para mostrar
  icon: string;
  createdAt?: number; // timestamp local — solo para optimistas (sin id)
}

// Las entradas optimistas (las que añadimos al hacer submit, sin id de
// Postgres todavía) caducan tras este tiempo. Cubre el caso de scrapes
// muy rápidos que pasan directos a 'activo' sin que lleguemos a ver el
// placeholder en el backend, dejando un fantasma en la lista para siempre.
const OPTIMISTIC_TTL_MS = 8_000;

// Estado de cuota diaria devuelto por GET /profile/quota (Slice 4).
// Sólo se pinta el contador si is_demo=true; los usuarios registrados
// no tienen cuota diaria (rate-limit por minuto sí, pero eso lo evita
// el dedup natural — no merece UI dedicada).
interface QuotaState {
  is_demo: boolean;
  ingest: { used: number; limit: number | null };
  chat: { used: number; limit: number | null };
}

export default function IngestPage() {
  const { token } = useAuthStore();
  const [urlsInput, setUrlsInput] = useState("");
  const [source, setSource] = useState("web");
  const [loading, setLoading] = useState(false);
  const [procesando, setProcesando] = useState<Procesando[]>([]);
  const [error, setError] = useState("");
  const [quota, setQuota] = useState<QuotaState | null>(null);

  // Refresca el estado de cuota desde el server (single source of truth).
  // Llamamos: al montar, tras cada submit (éxito o error), y cuando el
  // server devuelve 429 con scope=ip/global (para sincronizar contador).
  const refreshQuota = useCallback(async () => {
    if (!token) return;
    try {
      const q = await apiCall<QuotaState>("/profile/quota", {}, token);
      setQuota(q);
    } catch {
      /* silencioso — el counter es informativo, no bloqueante */
    }
  }, [token]);

  useEffect(() => { refreshQuota(); }, [refreshQuota]);

  // Helpers: ¿cuántos URLs puede enviar el usuario ahora mismo?
  const ingestRemaining =
    quota?.is_demo && quota.ingest.limit !== null
      ? Math.max(0, quota.ingest.limit - quota.ingest.used)
      : null;
  const isDemoBlocked = ingestRemaining !== null && ingestRemaining === 0;
  // Línea-a-línea: filtramos vacías para el contador en vivo del form.
  const pendingCount = urlsInput
    .split("\n")
    .map((u) => u.trim())
    .filter(Boolean).length;
  const wouldExceed =
    ingestRemaining !== null && pendingCount > ingestRemaining;

  // Carga los recursos en estado=procesando del backend para que sigan
  // visibles tras un refresh mientras la ingesta no haya completado.
  const loadProcesando = useCallback(async () => {
    if (!token) return;
    try {
      const data = await apiCall<{ id: string; url: string; titulo?: string }[]>(
        "/resources?estado=procesando&limit=50",
        {},
        token,
      );
      setProcesando((prev) => {
        const now = Date.now();
        // Mantén entradas optimistas (sin id) que aún no llegaron a Postgres,
        // pero descarta las que llevan más del TTL — son fantasmas de scrapes
        // muy rápidos que pasaron directos a 'activo'.
        const optimistic = prev.filter(
          (p) => !p.id && p.createdAt && now - p.createdAt < OPTIMISTIC_TTL_MS,
        );
        const fromBackend = data.map((r) => ({
          id: r.id,
          url: r.url,
          titulo: r.titulo,
          status: "Procesando...",
          icon: "⏳",
        }));
        // Evita duplicados entre optimistas y backend.
        const seen = new Set(fromBackend.map((p) => p.url));
        return [...fromBackend, ...optimistic.filter((p) => !seen.has(p.url))];
      });
    } catch {
      /* silencioso — la sección procesando es informativa, no bloqueante */
    }
  }, [token]);

  useEffect(() => { loadProcesando(); }, [loadProcesando]);

  // Polling de seguridad cada 20s — el SSE es el camino rápido, pero si por
  // algún motivo el navegador pierde el evento (reconexión silenciosa, tab
  // dormida), nos sincronizamos contra el backend que es la fuente de verdad
  // (ya filtra estado=procesando).
  useEffect(() => {
    if (!token) return;
    const interval = setInterval(loadProcesando, 20_000);
    const onVis = () => {
      if (document.visibilityState === "visible") loadProcesando();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [token, loadProcesando]);

  const sseFeedUrl = token ? sseUrl(token) : null;
  const { events, clear } = useSSE(sseFeedUrl, (ev) => {
    // Defensive: limpia optimistas por URL match.
    if (ev.url) {
      setProcesando((prev) => prev.filter((s) => s.url !== ev.url));
    }
    // Fuente de verdad: el backend ya devuelve solo estado=procesando, así
    // que tras la transición a activo el item desaparece de la lista solo.
    loadProcesando();
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const urls = urlsInput
      .split("\n")
      .map((u) => u.trim())
      .filter(Boolean);
    if (!urls.length) return;

    setLoading(true);
    setError("");
    const results: Procesando[] = [];

    const now = Date.now();
    for (const url of urls) {
      try {
        const resp = await apiCall<any>(
          "/ingest",
          { method: "POST", body: JSON.stringify({ url, source }) },
          token
        );
        const isDup = resp.is_duplicate;
        results.push({
          url,
          status: isDup ? "Duplicado — re-procesando" : "Encolada ✓",
          icon: isDup ? "⏭️" : "📥",
          createdAt: now,
        });
      } catch (err: any) {
        results.push({ url, status: `Error: ${err.message}`, icon: "❌", createdAt: now });
      }
    }
    setProcesando((prev) => [...results, ...prev]);
    setUrlsInput("");
    setLoading(false);
    // Tras un pequeño retraso, refrescamos para reemplazar las entradas
    // optimistas por las reales con id de Postgres (placeholder insertado).
    setTimeout(() => loadProcesando(), 800);
    // Sincroniza el contador con el server — relevante para demo.
    refreshQuota();
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 max-w-3xl mx-auto w-full">
      <div className="mb-6">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <Link2 className="w-5 h-5 text-accent-light" />
          Ingestar URLs
          <DemoHint
            hint="Las URLs que añadas se borran cuando expire tu sesión demo (15 min). Cuota diaria: 5 ingests por IP, con un cap global compartido entre todos los visitantes."
          />
        </h1>
        <p className="text-sm text-muted mt-1">
          Añade URLs a tu base de conocimiento. Aparecerán aquí cuando terminen de procesarse.
        </p>
      </div>

      {/* Cuota del demo — visible solo si is_demo=true (Slice 4) */}
      {quota?.is_demo && quota.ingest.limit !== null && (
        <div
          className={`mb-4 p-3 rounded-xl border flex items-start gap-2.5 ${
            isDemoBlocked
              ? "bg-red-900/15 border-red-700/40"
              : "bg-accent/8 border-accent/25"
          }`}
        >
          <Sparkles
            className={`w-4 h-4 flex-shrink-0 mt-0.5 ${
              isDemoBlocked ? "text-red-300" : "text-accent-light"
            }`}
          />
          <div className="text-xs leading-relaxed">
            <div className="flex items-center gap-2 mb-0.5">
              <span className="font-semibold text-slate-100">Demo público</span>
              <span
                className={`font-mono text-[11px] px-1.5 py-0.5 rounded ${
                  isDemoBlocked
                    ? "bg-red-900/30 text-red-200"
                    : "bg-card text-slate-300"
                }`}
              >
                {quota.ingest.used} / {quota.ingest.limit} ingests hoy
              </span>
            </div>
            <p className="text-muted">
              {isDemoBlocked
                ? "Has alcanzado el límite diario. Vuelve mañana o regístrate para uso ilimitado con tus propias claves."
                : `Te quedan ${ingestRemaining} URLs hoy. La cuota se resetea a medianoche UTC. Regístrate para uso ilimitado.`}
            </p>
          </div>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="bg-card border border-border rounded-2xl p-5 mb-6">
        <div className="flex gap-3 flex-wrap mb-4">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs text-muted mb-1.5">Fuente</label>
            <input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              disabled={isDemoBlocked}
              className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-100 outline-none focus:border-accent-light transition-colors disabled:opacity-50"
              placeholder="web"
            />
          </div>
        </div>

        <label className="block text-xs text-muted mb-1.5">
          URLs (una por línea)
          {ingestRemaining !== null && (
            <span className="ml-1 text-muted/70">
              · máx {ingestRemaining} por envío
            </span>
          )}
        </label>
        <textarea
          value={urlsInput}
          onChange={(e) => setUrlsInput(e.target.value)}
          rows={4}
          disabled={isDemoBlocked}
          placeholder={
            isDemoBlocked
              ? "Cuota diaria del demo agotada — vuelve mañana o regístrate."
              : "https://ejemplo.com/articulo\nhttps://otro.com/doc"
          }
          className="w-full bg-surface border border-border rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-muted outline-none focus:border-accent-light transition-colors font-mono resize-y disabled:opacity-50 disabled:cursor-not-allowed"
        />

        {wouldExceed && (
          <p className="text-amber-300 text-xs mt-2 flex items-center gap-1">
            <AlertCircle className="w-3.5 h-3.5" />
            Has escrito {pendingCount} URLs pero solo te quedan {ingestRemaining}.
            Recorta la lista antes de enviar.
          </p>
        )}

        {error && (
          <p className="text-red-400 text-sm mt-2 flex items-center gap-1">
            <AlertCircle className="w-3.5 h-3.5" />
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading || !urlsInput.trim() || isDemoBlocked || wouldExceed}
          className="mt-4 flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Plus className="w-4 h-4" />
          )}
          {loading ? "Enviando..." : "Ingestar URLs"}
        </button>
      </form>

      {/* Reactive feed — completed via SSE */}
      {events.length > 0 && (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-300 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-green-400" />
              Completadas ({events.length})
            </h2>
            <button
              onClick={clear}
              className="text-xs text-muted hover:text-slate-300 flex items-center gap-1 transition-colors"
            >
              <Trash2 className="w-3 h-3" />
              Limpiar
            </button>
          </div>
          <div className="space-y-2">
            <AnimatePresence>
              {events.map((ev, i) => (
                <motion.div
                  key={`${ev.recurso_id}-${i}`}
                  initial={{ opacity: 0, y: -8, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  className="bg-green-900/15 border border-green-700/30 rounded-xl p-3.5 flex items-start gap-3"
                >
                  <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-200 truncate">
                      {ev.titulo || ev.url}
                    </p>
                    <p className="text-xs text-muted truncate mt-0.5">{ev.url}</p>
                  </div>
                  <span className="ml-auto text-xs bg-green-800/30 text-green-300 px-2 py-0.5 rounded-full flex-shrink-0">
                    vectorizado
                  </span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Procesando (vivas en backend o recién enviadas) */}
      {procesando.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-1.5">
            <Loader2 className="w-4 h-4 text-amber-400 animate-spin" />
            Procesando ({procesando.length})
          </h2>
          <div className="space-y-2">
            {procesando.map((item, i) => (
              <div
                key={item.id ?? `opt-${i}`}
                className="bg-amber-900/10 border border-amber-700/30 rounded-xl p-3.5 flex items-center gap-3"
              >
                <span className="text-base flex-shrink-0">{item.icon}</span>
                <div className="min-w-0 flex-1">
                  {item.titulo && (
                    <p className="text-sm font-medium text-slate-200 truncate">{item.titulo}</p>
                  )}
                  <p className="text-xs font-mono text-muted truncate">{item.url}</p>
                  <p className="text-xs text-amber-300/80 mt-0.5">{item.status}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
