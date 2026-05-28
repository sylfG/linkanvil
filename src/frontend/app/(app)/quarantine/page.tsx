"use client";
import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  ExternalLink,
  RefreshCw,
  RotateCcw,
  Trash2,
  X,
  Hourglass,
  Sparkles,
  Hand,
  CalendarX,
} from "lucide-react";
import { apiCall } from "@/lib/api";
import { DemoHint } from "@/components/DemoHint";
import { useAuthStore } from "@/lib/auth";
import { useResourceStream, useResourceStreamDispatch } from "@/lib/resource_stream";
import { Pagination, PAGE_SIZE } from "@/components/Pagination";

interface QuarantineItem {
  id: string;
  url: string;
  titulo?: string;
  resumen?: string;
  categoria?: string;
  volatilidad?: string;
  fecha_caducidad?: string;
  quarantined_at: string;
  quarantine_reason: "caducidad" | "colision_semantica" | "manual" | "evento_pasado";
  quarantine_grace_until: string;
  dias_restantes: number;
}

const REASON_META: Record<
  string,
  { label: string; icon: React.ComponentType<{ className?: string }>; cls: string }
> = {
  caducidad: {
    label: "Caducidad",
    icon: Hourglass,
    cls: "bg-amber-800/30 text-amber-300 border-amber-700/30",
  },
  colision_semantica: {
    label: "Reemplazo semántico",
    icon: Sparkles,
    cls: "bg-violet-800/30 text-violet-300 border-violet-700/30",
  },
  manual: {
    label: "Manual",
    icon: Hand,
    cls: "bg-slate-800/30 text-slate-300 border-slate-700/30",
  },
  evento_pasado: {
    label: "Evento pasado",
    icon: CalendarX,
    cls: "bg-blue-800/30 text-blue-300 border-blue-700/30",
  },
};

function daysClass(days: number): string {
  if (days <= 3) return "text-red-300";
  if (days <= 7) return "text-amber-300";
  return "text-green-300";
}

export default function QuarantinePage() {
  const { token } = useAuthStore();
  const [items, setItems] = useState<QuarantineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{ id: string; action: "expire" | "delete" } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const dispatchEvent = useResourceStreamDispatch();

  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  const pageItems = items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  useEffect(() => {
    if (page > totalPages) setPage(1);
  }, [page, totalPages]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiCall<{ items: QuarantineItem[]; count: number }>(
        "/resources/quarantine?limit=200",
        {},
        token,
      );
      setItems(data.items);
    } catch (e: any) {
      setError(e.message ?? "Error cargando bandeja");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  // Refresca al volver a la pestaña visible (red de seguridad).
  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [load]);

  // SSE: cualquier transición de recurso (otra pestaña, cron, otro device)
  // dispara un re-fetch inmediato.
  useResourceStream(token, () => { load(); });

  function fireOptimistic(id: string, evento_tipo: "recurso.rescatado" | "recurso.expirado" | "recurso.eliminado") {
    const item = items.find((it) => it.id === id);
    dispatchEvent({
      evento_tipo,
      recurso_id: id,
      url: item?.url,
      titulo: item?.titulo,
      motivo: "manual",
      created_at: new Date().toISOString(),
      optimistic: true,
    });
  }

  async function rescue(id: string) {
    setBusyId(id);
    try {
      await apiCall(`/resources/${id}/rescue`, { method: "POST" }, token);
      fireOptimistic(id, "recurso.rescatado");
      setItems((prev) => prev.filter((it) => it.id !== id));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function expire(id: string) {
    setBusyId(id);
    setConfirm(null);
    try {
      await apiCall(`/resources/${id}/expire`, { method: "POST" }, token);
      fireOptimistic(id, "recurso.expirado");
      setItems((prev) => prev.filter((it) => it.id !== id));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function remove(id: string) {
    setBusyId(id);
    setConfirm(null);
    try {
      await apiCall(`/resources/${id}`, { method: "DELETE" }, token);
      fireOptimistic(id, "recurso.eliminado");
      setItems((prev) => prev.filter((it) => it.id !== id));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 w-full">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            Bandeja de cuarentena
            <DemoHint
              hint="Antes del audit del minuto 5 verás aquí solo el ejemplo seed (ExpoJove 2024). Después del minuto 5 aparecerán 2 de tus recursos efímeros transicionados con motivo 'caducidad'."
            />
          </h1>
          <p className="text-sm text-muted mt-1">
            {items.length} recurso(s) pendiente(s) de revisión antes del archivado definitivo.
          </p>
        </div>
        <button
          onClick={load}
          className="p-2 rounded-lg bg-card border border-border text-muted hover:text-slate-200 transition-colors"
          title="Actualizar"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-900/20 border border-red-700/30 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-card border border-border rounded-xl p-4 animate-pulse">
              <div className="h-4 bg-border rounded w-3/4 mb-2" />
              <div className="h-3 bg-border rounded w-1/2 mb-3" />
              <div className="h-3 bg-border rounded w-full" />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center opacity-50">
          <AlertTriangle className="w-10 h-10 mb-3" />
          <p className="font-medium">Bandeja vacía</p>
          <p className="text-sm text-muted mt-1">
            No hay recursos pendientes de revisión.
          </p>
        </div>
      ) : (
        <motion.ul
          className="grid grid-cols-1 lg:grid-cols-2 gap-3"
          initial="hidden"
          animate="visible"
          variants={{ visible: { transition: { staggerChildren: 0.03 } }, hidden: {} }}
        >
          {pageItems.map((it) => {
            const meta = REASON_META[it.quarantine_reason] ?? REASON_META.manual;
            const Icon = meta.icon;
            const busy = busyId === it.id;
            return (
              <motion.li
                key={it.id}
                variants={{
                  hidden: { opacity: 0, y: 12 },
                  visible: { opacity: 1, y: 0, transition: { duration: 0.2 } },
                }}
                className="bg-card border border-border rounded-xl p-4 flex flex-col gap-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-sm font-medium text-slate-100 leading-snug line-clamp-2 flex-1">
                    {it.titulo || it.url}
                  </h3>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full border flex items-center gap-1 flex-shrink-0 ${meta.cls}`}
                  >
                    <Icon className="w-3 h-3" />
                    {meta.label}
                  </span>
                </div>

                <a
                  href={it.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs font-mono text-muted hover:text-accent-light transition-colors truncate"
                >
                  <ExternalLink className="w-3 h-3 flex-shrink-0" />
                  <span className="truncate">{it.url}</span>
                </a>

                {it.resumen && (
                  <p className="text-xs text-slate-400 line-clamp-2">{it.resumen}</p>
                )}

                <div className="flex items-center justify-between text-xs">
                  <span className={`font-medium ${daysClass(it.dias_restantes)}`}>
                    {it.dias_restantes > 0
                      ? `${it.dias_restantes} día(s) restante(s)`
                      : "Expira hoy"}
                  </span>
                  <span className="text-muted">
                    Hasta {new Date(it.quarantine_grace_until).toLocaleDateString("es-ES")}
                  </span>
                </div>

                <div className="flex gap-2 pt-1 border-t border-border/60">
                  <button
                    disabled={busy}
                    onClick={() => rescue(it.id)}
                    className="flex-1 flex items-center justify-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-green-900/20 text-green-300 border border-green-700/30 hover:bg-green-900/40 transition-colors disabled:opacity-40"
                  >
                    <RotateCcw className="w-3 h-3" />
                    Rescatar
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => setConfirm({ id: it.id, action: "expire" })}
                    className="flex-1 flex items-center justify-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-amber-900/20 text-amber-300 border border-amber-700/30 hover:bg-amber-900/40 transition-colors disabled:opacity-40"
                  >
                    <Hourglass className="w-3 h-3" />
                    Archivar
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => setConfirm({ id: it.id, action: "delete" })}
                    className="flex items-center justify-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-red-900/20 text-red-300 border border-red-700/30 hover:bg-red-900/40 transition-colors disabled:opacity-40"
                    title="Eliminar definitivamente"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </motion.li>
            );
          })}
        </motion.ul>
      )}

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={items.length}
        onChange={setPage}
      />

      <AnimatePresence>
        {confirm && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/60"
              onClick={() => setConfirm(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="fixed inset-0 z-50 flex items-center justify-center p-4"
            >
              <div className="bg-surface border border-border rounded-2xl shadow-2xl max-w-sm w-full p-5">
                <div className="flex items-start gap-3 mb-4">
                  <div className="w-10 h-10 rounded-full bg-red-900/30 flex items-center justify-center flex-shrink-0">
                    {confirm.action === "delete" ? (
                      <Trash2 className="w-5 h-5 text-red-400" />
                    ) : (
                      <Hourglass className="w-5 h-5 text-amber-400" />
                    )}
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-sm">
                      {confirm.action === "delete"
                        ? "¿Eliminar definitivamente?"
                        : "¿Confirmar archivado?"}
                    </h3>
                    <p className="text-xs text-muted mt-1">
                      {confirm.action === "delete"
                        ? "Borra el recurso de tu base de conocimiento. Si nadie más lo tiene, se elimina globalmente y de Qdrant. No se puede deshacer."
                        : "Lo archiva inmediatamente, sin esperar al fin del período de gracia."}
                    </p>
                  </div>
                  <button
                    onClick={() => setConfirm(null)}
                    className="p-1 rounded-lg hover:bg-white/5 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => setConfirm(null)}
                    className="px-3 py-1.5 text-xs rounded-lg bg-card border border-border text-muted hover:text-slate-200 transition-colors"
                  >
                    Cancelar
                  </button>
                  <button
                    onClick={() =>
                      confirm.action === "delete" ? remove(confirm.id) : expire(confirm.id)
                    }
                    className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                      confirm.action === "delete"
                        ? "bg-red-700 hover:bg-red-600 text-white"
                        : "bg-amber-700 hover:bg-amber-600 text-white"
                    }`}
                  >
                    Sí, continuar
                  </button>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
